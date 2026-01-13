# blackjack_backend.py
# Single Deck Blackjack (Hit/Stand only)
# Dealer rule: hit < 17, stand > 17, hard 17 stand, SOFT 17 hit with 50% probability.
#
# Demo goals:
# - Clean one-hand trace for UI
# - "Exchanges" mode: run 5 exchanges, each exchange is a mini-series of N random hands per bot
#   to greatly reduce ties while keeping realism/randomness.
#
# Run:
#   python blackjack_backend.py

# Both DealerBot(EV) and PlayerBot(Naive) agents are implemented, DealerBot uses exact EV calculations,
# while PlayerBot uses a naive fixed threshold strategy, hitting on totals below or equal to 16 and standing otherwise.

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Tuple, List, Any, Optional
import random


# Deck model

# Blackjack uses a finite deck with repeated card values.
# We represent a single deck as a tuple of counts:
#   (A,2,3,4,5,6,7,8,9,10-value)
# where 10-value includes 10/J/Q/K (16 cards total).
#
# This section provides:
# - A standard "full single deck" count vector
# - Helper functions to remove a drawn card from the deck counts
# - Probability iteration over remaining cards (iter_draws)
# - Random drawing from the remaining deck (draw_random)

CARD_VALUES = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
Deck = Tuple[int, ...]  


def full_single_deck_counts() -> Deck:
    return (4, 4, 4, 4, 4, 4, 4, 4, 4, 16)


def total_cards(deck: Deck) -> int:
    return sum(deck)


def _idx_for_value(v: int) -> int:
    if v == 1:
        return 0
    if 2 <= v <= 9:
        return v - 1
    if v == 10:
        return 9
    raise ValueError(f"Invalid card value: {v}")


def dec_count(deck: Deck, v: int) -> Deck:
    i = _idx_for_value(v)
    if deck[i] <= 0:
        raise ValueError(f"No remaining card of value {v} in deck.")
    lst = list(deck)
    lst[i] -= 1
    return tuple(lst)


def iter_draws(deck: Deck):
    
    n = total_cards(deck)
    if n == 0:
        return
    for v in CARD_VALUES:
        i = _idx_for_value(v)
        c = deck[i]
        if c > 0:
            yield v, c / n


def draw_random(deck: Deck) -> Tuple[int, Deck]:
    
    n = total_cards(deck)
    if n <= 0:
        raise ValueError("Cannot draw from empty deck.")
    r = random.randrange(n)
    acc = 0
    for v in CARD_VALUES:
        i = _idx_for_value(v)
        c = deck[i]
        if c <= 0:
            continue
        if acc + c > r:
            return v, dec_count(deck, v)
        acc += c
    raise RuntimeError("Deck inconsistent.")



# Hand model

# A blackjack hand is summarized by:
# - total: the current numeric total of the hand
# - usable_aces: number of aces currently counted as 11
#
# This is the standard RL/AI representation of blackjack hands:
# it allows us to correctly handle "soft" totals (hands where an ace
# can be downgraded from 11 to 1 to avoid busting).
#
# The add(card) method:
# - adds a card value to the hand
# - treats aces as 11 when safe, else 1
# - automatically converts aces from 11 -> 1 as needed to prevent bust

@dataclass(frozen=True)
class Hand:
    total: int
    usable_aces: int  # number of aces currently counted as 11

    @staticmethod
    def empty() -> "Hand":
        return Hand(total=0, usable_aces=0)

    def add(self, card_value: int) -> "Hand":
        t = self.total
        ua = self.usable_aces

        if card_value == 1:  # Ace
            if t + 11 <= 21:
                t += 11
                ua += 1
            else:
                t += 1
        else:
            t += card_value

        while t > 21 and ua > 0:
            t -= 10
            ua -= 1

        return Hand(total=t, usable_aces=ua)

    @property
    def is_soft(self) -> bool:
        return self.usable_aces > 0

    @property
    def is_bust(self) -> bool:
        return self.total > 21



@dataclass
class Step:
    actor: str          # "SYSTEM" / "PLAYER" / "DEALER"
    action: str         # "DEAL" / "HIT" / "STAND" / "DRAW"
    card: Optional[int] 
    player_total: int
    dealer_total: int
    note: str = ""


class Tracer:
    def __init__(self) -> None:
        self.steps: List[Step] = []

    def emit(
        self,
        actor: str,
        action: str,
        card: Optional[int],
        player_total: int,
        dealer_total: int,
        note: str = "",
    ) -> None:
        self.steps.append(Step(actor, action, card, player_total, dealer_total, note))


# Dealer exact outcome probabilities

# ------------------------------------------------------------
# The EV agent must evaluate "stand" by estimating what the dealer will
# end up with (17-21 or bust) given the dealer upcard and remaining deck.
#
# We compute an exact probability distribution for the dealer's final
# result using recursion over possible dealer draws.
#
# Dealer policy implemented:
# - Hit while total < 17
# - Stand while total > 17
# - Hard 17: Stand
# - Soft 17: Hit with 50% probability, Stand with 50% probability
#
# dealer_final_dist(...) returns a distribution over outcomes:
#   {17: p17, 18: p18, ..., 21: p21, "bust": pbust}
#
# We memoize dealer_final_dist with lru_cache to avoid recomputing the
# same states, since EV calculations call it many times.

OutcomeKey = object
OutcomeDist = Dict[OutcomeKey, float]


def _merge_dist(dst: OutcomeDist, src: OutcomeDist, weight: float) -> None:
    for k, p in src.items():
        dst[k] = dst.get(k, 0.0) + weight * p


@lru_cache(maxsize=None)
def dealer_final_dist(hand_total: int, usable_aces: int, deck: Deck) -> Tuple[Tuple[OutcomeKey, float], ...]:

    # Dealer Rules: Hit below 17, stand above 17, hard 17 stand, SOFT 17 hit with 50% probability.

    hand = Hand(hand_total, usable_aces)

    if hand.total > 21:
        return (("bust", 1.0),)

    if hand.total > 17:
        return ((hand.total, 1.0),)

    if hand.total == 17 and not hand.is_soft:
        return ((17, 1.0),)

    dist: OutcomeDist = {}

    if hand.total == 17 and hand.is_soft:
        dist[17] = dist.get(17, 0.0) + 0.5
        hit_weight = 0.5
    else:
        hit_weight = 1.0

    if hit_weight > 0.0:
        for v, p in iter_draws(deck):
            deck2 = dec_count(deck, v)
            new_hand = hand.add(v)
            sub = dict(dealer_final_dist(new_hand.total, new_hand.usable_aces, deck2))
            _merge_dist(dist, sub, hit_weight * p)

    s = sum(dist.values())
    if s > 0:
        for k in list(dist.keys()):
            dist[k] /= s

    return tuple(sorted(dist.items(), key=lambda x: str(x[0])))


def dealer_dist_from_upcard(upcard_value: int, deck_after_upcard: Deck) -> OutcomeDist:
    base = Hand.empty().add(upcard_value)
    dist: OutcomeDist = {}

    for hole, p_hole in iter_draws(deck_after_upcard):
        deck2 = dec_count(deck_after_upcard, hole)
        start = base.add(hole)
        sub = dict(dealer_final_dist(start.total, start.usable_aces, deck2))
        _merge_dist(dist, sub, p_hole)

    s = sum(dist.values())
    for k in list(dist.keys()):
        dist[k] /= s
    return dist


# Player EV (Hit vs Stand) with recursion + memoization

# This is the core AI logic.
#
# We model player payoff as:
#   +1 for win, 0 for push, -1 for loss
#
# EV(stand):
# - Compute the dealer's final-outcome distribution
# - Compare player total to each dealer outcome
# - Sum payoff * probability across outcomes
#
# EV(hit):
# - Consider every possible next card from the remaining deck
# - For each card, update the hand and recurse to the best future EV
#
# ev_optimal(...) computes:
#   max(EV(hit), EV(stand))
# from a given game state.
#
# This recursion is like an "expectation" decision tree:
# - chance nodes = random draws
# - decision nodes = hit or stand
#
# We memoize ev_optimal to make the runtime practical.

def ev_stand(player_hand: Hand, dealer_upcard: int, deck: Deck) -> float:
    d = dealer_dist_from_upcard(dealer_upcard, deck)
    ev = 0.0
    for outcome, p in d.items():
        if outcome == "bust":
            ev += p * 1.0
        else:
            dealer_total = int(outcome)
            if player_hand.total > dealer_total:
                ev += p * 1.0
            elif player_hand.total < dealer_total:
                ev += p * -1.0
            else:
                ev += 0.0
    return ev


@lru_cache(maxsize=None)
def ev_optimal(player_total: int, player_usable_aces: int, dealer_upcard: int, deck: Deck) -> float:
    hand = Hand(player_total, player_usable_aces)
    if hand.total > 21:
        return -1.0
    s = ev_stand(hand, dealer_upcard, deck)
    h = ev_hit(hand, dealer_upcard, deck)
    return max(s, h)


def ev_hit(player_hand: Hand, dealer_upcard: int, deck: Deck) -> float:
    ev = 0.0
    for v, p in iter_draws(deck):
        deck2 = dec_count(deck, v)
        new_hand = player_hand.add(v)
        ev += p * ev_optimal(new_hand.total, new_hand.usable_aces, dealer_upcard, deck2)
    return ev


# Individual Agents

# We define two agents so we can compare a smarter strategy to a baseline.
#
# EVAgent:
# - Computes EV(hit) and EV(stand) from the current state
# - Chooses the action with higher expected return
# - Uses the dealer model + remaining deck composition
#
# NaiveAgent:
# - Simple baseline rule: hit if total <= threshold, else stand
# - Does not model dealer, probabilities, or deck composition
# - Acts as a comparison point (control group)

class EVAgent:
    name = "DealerBot(EV)"

    def choose(self, player_hand: Hand, dealer_upcard: int, deck: Deck) -> str:
        if player_hand.total > 21:
            return "STAND"
        s = ev_stand(player_hand, dealer_upcard, deck)
        h = ev_hit(player_hand, dealer_upcard, deck)
        return "HIT" if h > s else "STAND"


class NaiveAgent:
    name = "PlayerBot(Naive)"

    def __init__(self, hit_below: int = 16):
        self.hit_below = hit_below

    def choose(self, player_hand: Hand, dealer_upcard: int, deck: Deck) -> str:
        return "HIT" if player_hand.total <= self.hit_below else "STAND"


# This section simulates real blackjack hands using the deck counts.
#
# resolve(...) computes payoff after both player and dealer finish:
# - player bust => loss
# - dealer bust => win
# - otherwise compare totals
#
# deal_initial_* deals the standard 4-card starting state:
# - player card 1
# - dealer upcard
# - player card 2
# - dealer hole card
#
# dealer_play_sim(...) plays the dealer's forced policy until stand/bust.
#
# play_hand_with_trace(...) runs a full hand and emits clean trace steps
# for UI animation and demo output.
#
# play_one_hand(...) is a faster version used for bulk simulations
# (no tracing, for performance evaluation).


def resolve(player_hand: Hand, dealer_hand: Hand) -> int:
    """+1 win, -1 loss, 0 push"""
    if player_hand.total > 21:
        return -1
    if dealer_hand.total > 21:
        return 1
    if player_hand.total > dealer_hand.total:
        return 1
    if player_hand.total < dealer_hand.total:
        return -1
    return 0


def deal_initial_with_trace(deck: Deck, tracer: Tracer, reveal_hole: bool = True) -> Tuple[Hand, Hand, int, Deck]:
    p = Hand.empty()
    d = Hand.empty()

    c, deck = draw_random(deck); p = p.add(c)
    tracer.emit("PLAYER", "DEAL", c, p.total, d.total, "player card 1")

    c, deck = draw_random(deck); d = d.add(c); upcard = c
    tracer.emit("DEALER", "DEAL", c, p.total, d.total, "dealer upcard")

    c, deck = draw_random(deck); p = p.add(c)
    tracer.emit("PLAYER", "DEAL", c, p.total, d.total, "player card 2")

    c, deck = draw_random(deck); d = d.add(c)
    tracer.emit("DEALER", "DEAL", c if reveal_hole else None, p.total, d.total,
                "dealer hole" if reveal_hole else "dealer hole (hidden)")

    return p, d, upcard, deck


def deal_initial_no_trace(deck: Deck) -> Tuple[Hand, Hand, int, Deck]:
    p = Hand.empty()
    d = Hand.empty()

    c, deck = draw_random(deck); p = p.add(c)
    c, deck = draw_random(deck); d = d.add(c); upcard = c
    c, deck = draw_random(deck); p = p.add(c)
    c, deck = draw_random(deck); d = d.add(c)

    return p, d, upcard, deck


def dealer_play_sim(
    dealer_hand: Hand,
    deck: Deck,
    tracer: Optional[Tracer] = None,
    player_total_for_ui: int = -1,
) -> Tuple[Hand, Deck]:
    while True:
        if dealer_hand.total > 21:
            return dealer_hand, deck
        if dealer_hand.total > 17:
            return dealer_hand, deck
        if dealer_hand.total < 17:
            c, deck = draw_random(deck)
            dealer_hand = dealer_hand.add(c)
            if tracer:
                tracer.emit("DEALER", "DRAW", c, player_total_for_ui, dealer_hand.total, "")
            continue

        # total == 17
        if not dealer_hand.is_soft:
            return dealer_hand, deck

        # soft 17: 50% to hit for an element of randomness
        if random.random() < 0.5:
            c, deck = draw_random(deck)
            dealer_hand = dealer_hand.add(c)
            if tracer:
                tracer.emit("DEALER", "DRAW", c, player_total_for_ui, dealer_hand.total, "soft 17 hit (50%)")
        else:
            return dealer_hand, deck


def play_hand_with_trace(agent, seed: Optional[int] = None, reveal_hole: bool = True) -> Tuple[int, List[Step], Dict[str, Any]]:
    if seed is not None:
        random.seed(seed)

    deck = full_single_deck_counts()
    tracer = Tracer()

    p_hand, d_hand, upcard, deck = deal_initial_with_trace(deck, tracer, reveal_hole=reveal_hole)

    while not p_hand.is_bust:
        action = agent.choose(p_hand, upcard, deck)
        tracer.emit("PLAYER", action, None, p_hand.total, d_hand.total, f"{agent.name} decision")
        if action == "STAND":
            break
        c, deck = draw_random(deck)
        p_hand = p_hand.add(c)
        tracer.emit("PLAYER", "DRAW", c, p_hand.total, d_hand.total, "")

    if p_hand.is_bust:
        payoff = -1
        summary = {
            "agent": agent.name,
            "dealer_upcard": upcard,
            "player_total": p_hand.total,
            "dealer_total": d_hand.total,
            "player_bust": True,
            "dealer_bust": False,
            "payoff": payoff,
        }
        return payoff, tracer.steps, summary

    d_final, deck = dealer_play_sim(d_hand, deck, tracer=tracer, player_total_for_ui=p_hand.total)
    payoff = resolve(p_hand, d_final)

    summary = {
        "agent": agent.name,
        "dealer_upcard": upcard,
        "player_total": p_hand.total,
        "dealer_total": d_final.total,
        "player_bust": False,
        "dealer_bust": d_final.total > 21,
        "payoff": payoff,
    }
    return payoff, tracer.steps, summary


def play_one_hand(agent) -> int:
    deck = full_single_deck_counts()
    p_hand, d_hand, upcard, deck = deal_initial_no_trace(deck)

    while not p_hand.is_bust:
        action = agent.choose(p_hand, upcard, deck)
        if action == "STAND":
            break
        c, deck = draw_random(deck)
        p_hand = p_hand.add(c)

    if p_hand.is_bust:
        return -1

    d_final, deck = dealer_play_sim(d_hand, deck, tracer=None, player_total_for_ui=-1)
    return resolve(p_hand, d_final)

# run_match runs many independent simulated hands for each agent and
# collects:
# - wins, losses, pushes
# - average return per hand (mean payoff)
#
# Average return is a key objective metric:
#   avg_return = (wins - losses) / hands
#
# A fixed seed can be used for reproducible experiments.
# Seed=None produces fresh randomness each run.

def run_match(agent_a, agent_b, hands: int = 10000, seed: Optional[int] = 1234) -> Dict[str, Any]:
    if seed is not None:
        random.seed(seed)

    def stats_for(agent) -> Dict[str, Any]:
        w = l = pu = 0
        total = 0
        for _ in range(hands):
            payoff = play_one_hand(agent)
            total += payoff
            if payoff == 1:
                w += 1
            elif payoff == -1:
                l += 1
            else:
                pu += 1
        return {
            "agent": getattr(agent, "name", agent.__class__.__name__),
            "hands": hands,
            "wins": w,
            "losses": l,
            "pushes": pu,
            "avg_return": total / hands,
        }

    return {"A": stats_for(agent_a), "B": stats_for(agent_b)}


def _payoff_label(p: int) -> str:
    return "WIN" if p == 1 else ("LOSS" if p == -1 else "PUSH")


# In a live demo, comparing agents hand-by-hand can produce many ties,
# because each single hand only returns {-1, 0, +1}.
#
# To make "wins" clearer for an audience, we group hands into exchanges:
# - Each exchange = N hands played by each agent (all random)
# - Score = sum of payoffs across the N hands
# - Higher score wins the exchange
#
# This keeps realism (random hands) but reduces ties because the total
# score range becomes [-N..N], which is much more granular.

def run_demo_exchanges(agent_a, agent_b, exchanges: int = 5, hands_per_exchange: int = 7) -> None:
    """
    Real randomness per hand, but fewer ties:
      Each exchange = each agent plays `hands_per_exchange` independent random hands.
      Compare total score (sum of payoffs) to declare exchange winner.

    Ties become much rarer because totals range from [-N..N].
    """
    a_exchange_wins = b_exchange_wins = ties = 0

    print(f"\n=== Demo: {exchanges} exchanges, {hands_per_exchange} hands per exchange ===")
    print(f"Scoring per hand: WIN=+1, PUSH=0, LOSS=-1\n")

    for ex in range(1, exchanges + 1):
        a_total = 0
        b_total = 0
        a_w = a_l = a_p = 0
        b_w = b_l = b_p = 0

        for _ in range(hands_per_exchange):
            pa = play_one_hand(agent_a)
            pb = play_one_hand(agent_b)

            a_total += pa
            b_total += pb

            if pa == 1: a_w += 1
            elif pa == -1: a_l += 1
            else: a_p += 1

            if pb == 1: b_w += 1
            elif pb == -1: b_l += 1
            else: b_p += 1

        if a_total > b_total:
            winner = agent_a.name
            a_exchange_wins += 1
        elif b_total > a_total:
            winner = agent_b.name
            b_exchange_wins += 1
        else:
            winner = "TIE"
            ties += 1

        print(
            f"Exchange {ex}: "
            f"{agent_a.name} score={a_total:+d} (W{a_w}/L{a_l}/P{a_p}), "
            f"{agent_b.name} score={b_total:+d} (W{b_w}/L{b_l}/P{b_p}) "
            f"-> Winner: {winner}"
        )

    print(
        f"\nSeries result: {agent_a.name} wins={a_exchange_wins}, "
        f"{agent_b.name} wins={b_exchange_wins}, ties={ties}\n"
    )


# CLI demo

# The main block lets us quickly switch between:
# - One-hand trace (for showing a single animated hand in the demo)
# - Demo exchanges (for showing which bot is stronger in short runs)
# - Bulk match results (for report-grade evaluation with many hands)
#
# This supports both:
# - Presentation needs (fast, readable, engaging)
# - Report needs (large simulation, objective metrics)

def _pretty_card(v: Optional[int]) -> str:
    if v is None:
        return "?"
    if v == 1:
        return "A"
    if v == 10:
        return "10"
    return str(v)


def demo_multiple_hands(agent, num_hands: int = 3) -> None:

    for i in range(1, num_hands + 1):
        payoff, steps, summary = play_hand_with_trace(agent, seed=None, reveal_hole=True)

        print(f"\n=== Hand {i} Trace ===")
        print(f"Agent: {summary['agent']} | Dealer upcard: {_pretty_card(summary['dealer_upcard'])}\n")

        for s in steps:
            print(
                f"{s.actor:6} {s.action:5} {_pretty_card(s.card):>2} | "
                f"p={s.player_total:>2} d={s.dealer_total:>2} | {s.note}"
            )

        print("\n--- Result ---")
        print(
            f"Player total: {summary['player_total']} | "
            f"Dealer total: {summary['dealer_total']} | "
            f"payoff: {summary['payoff']}"
        )
        print("Payoff meaning: +1 win, 0 push, -1 loss")



if __name__ == "__main__":
    SHOW_MULTIPLE_HAND_TRACES = True
    NUM_HAND_TRACES = 1

    ONE_HAND_SEED = None  # None => random trace each run; set e.g. 42 for reproducible

    RUN_DEMO_EXCHANGES = True
    DEMO_EXCHANGES = 5
    HANDS_PER_EXCHANGE = 7  # increase to reduce ties even more (e.g., 11 or 15)

    RUN_BULK_MATCH_RESULTS = False   # turn ON for report
    BULK_HANDS = 50000
    BULK_SEED: Optional[int] = None  # set None for random bulk results
    

    ev_agent = EVAgent()
    naive_agent = NaiveAgent(hit_below=16)

    if SHOW_MULTIPLE_HAND_TRACES:
        demo_multiple_hands(ev_agent, num_hands=NUM_HAND_TRACES)


    if RUN_DEMO_EXCHANGES:
        run_demo_exchanges(ev_agent, naive_agent, exchanges=DEMO_EXCHANGES, hands_per_exchange=HANDS_PER_EXCHANGE)

    if RUN_BULK_MATCH_RESULTS:
        results = run_match(ev_agent, naive_agent, hands=BULK_HANDS, seed=BULK_SEED)
        print("=== Match results (bulk) ===")
        for key in ("A", "B"):
            r = results[key]
            print(f"{r['agent']}: wins={r['wins']} losses={r['losses']} pushes={r['pushes']} avg_return={r['avg_return']:.4f}")