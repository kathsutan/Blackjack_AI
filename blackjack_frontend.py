"""
Friendly Web-Based UI for Blackjack Game
Uses Flask for backend serving and HTML/CSS/JS for frontend
"""

from flask import Flask, render_template, jsonify, request
import json
from blackjack_backend import EVAgent, NaiveAgent, play_hand_with_trace, run_match
import os

app = Flask(__name__)

# Initialize agents
ev_agent = EVAgent()
naive_agent = NaiveAgent(hit_below=16)

# Session state
session_data = {
    "current_hand": None,
    "selected_agent": "EV"
}

@app.route('/')
def index():
    """Serve the main UI page"""
    return render_template('index.html')

@app.route('/api/agents')
def get_agents():
    """Get available agents"""
    return jsonify({
        "agents": [
            {"id": "EV", "name": "DealerBot (EV)", "description": "Uses exact EV calculations - smarter!"},
            {"id": "NAIVE", "name": "PlayerBot (Naive)", "description": "Uses simple hit/stand threshold"}
        ]
    })

@app.route('/api/play-hand', methods=['POST'])
def play_hand():
    """Play a single hand and get the trace"""
    data = request.json
    agent_id = data.get('agent_id', 'EV')
    seed = data.get('seed')
    
    agent = ev_agent if agent_id == 'EV' else naive_agent
    
    try:
        payoff, steps, summary = play_hand_with_trace(agent, seed=seed, reveal_hole=True)
        
        # Format steps for frontend
        formatted_steps = []
        for step in steps:
            formatted_steps.append({
                "actor": step.actor,
                "action": step.action,
                "card": step.card,
                "player_total": step.player_total,
                "dealer_total": step.dealer_total,
                "note": step.note
            })
        
        return jsonify({
            "success": True,
            "payoff": payoff,
            "steps": formatted_steps,
            "summary": summary
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/match', methods=['POST'])
def run_match_api():
    """Run a match between two agents"""
    data = request.json
    num_hands = data.get('num_hands', 1000)
    seed = data.get('seed')
    
    try:
        results = run_match(ev_agent, naive_agent, hands=num_hands, seed=seed)
        return jsonify({
            "success": True,
            "results": results
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/card-image', methods=['GET'])
def get_card_image():
    """Return card as emoji or unicode representation"""
    card_val = request.args.get('card')
    
    card_map = {
        '1': '🅰️',   # Ace
        '2': '2️⃣',
        '3': '3️⃣',
        '4': '4️⃣',
        '5': '5️⃣',
        '6': '6️⃣',
        '7': '7️⃣',
        '8': '8️⃣',
        '9': '9️⃣',
        '10': '🔟',
        'None': '🂠'  # Card back
    }
    
    return jsonify({"emoji": card_map.get(str(card_val), '?')})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
