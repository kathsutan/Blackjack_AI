// Global State
let selectedAgent = 'EV';
const cardEmojis = {
    1: '🅰️',
    2: '2️⃣',
    3: '3️⃣',
    4: '4️⃣',
    5: '5️⃣',
    6: '6️⃣',
    7: '7️⃣',
    8: '8️⃣',
    9: '9️⃣',
    10: '🔟'
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadAgents();
    setupTabNavigation();
    setupEventListeners();
});

// Load Available Agents
async function loadAgents() {
    try {
        const response = await fetch('/api/agents');
        const data = await response.json();
        
        const selector = document.getElementById('agent-selector');
        selector.innerHTML = '';
        
        data.agents.forEach(agent => {
            const card = document.createElement('div');
            card.className = `agent-card ${agent.id === 'EV' ? 'selected' : ''}`;
            card.innerHTML = `
                <h4>${agent.name}</h4>
                <p>${agent.description}</p>
            `;
            card.onclick = () => selectAgent(agent.id, agent.name);
            selector.appendChild(card);
        });
    } catch (error) {
        console.error('Failed to load agents:', error);
    }
}

// Select Agent
function selectAgent(agentId, agentName) {
    selectedAgent = agentId;
    document.querySelectorAll('.agent-card').forEach((card, index) => {
        card.classList.toggle('selected', (index === 0 && agentId === 'EV') || (index === 1 && agentId === 'NAIVE'));
    });
}

// Tab Navigation
function setupTabNavigation() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const tabName = e.target.getAttribute('data-tab');
            showTab(tabName);
        });
    });
}

function showTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active state from all buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    const tabId = `${tabName}-tab`;
    const tab = document.getElementById(tabId);
    if (tab) {
        tab.classList.add('active');
    }
    
    // Add active state to clicked button
    event.target.classList.add('active');
}

// Setup Event Listeners
function setupEventListeners() {
    // Play Hand Button
    document.getElementById('play-btn').addEventListener('click', playHand);
    
    // Run Tournament Button
    document.getElementById('run-tournament-btn').addEventListener('click', runTournament);
}

// Play Single Hand
async function playHand() {
    const seed = document.getElementById('seed-input').value || null;
    const btn = document.getElementById('play-btn');
    const loading = document.getElementById('loading');
    const gameContent = document.getElementById('game-content');
    const welcome = document.getElementById('welcome-message');
    
    btn.disabled = true;
    loading.style.display = 'block';
    
    try {
        const response = await fetch('/api/play-hand', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                agent_id: selectedAgent,
                seed: seed ? parseInt(seed) : null
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            displayHand(data, selectedAgent);
            welcome.style.display = 'none';
            gameContent.style.display = 'block';
        } else {
            alert('Error playing hand: ' + data.error);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to play hand');
    } finally {
        btn.disabled = false;
        loading.style.display = 'none';
    }
}

// Display Hand Results
function displayHand(data, agentId) {
    const summary = data.summary;
    const steps = data.steps;
    
    // Display Cards and game state
    displayGameTable(summary, steps);
    
    // Display Result
    displayResult(data.payoff, summary);
    
    // Display Trace
    displayTrace(steps);
}

// Display Game Table with Cards
function displayGameTable(summary, steps) {
    const playerCardsDiv = document.getElementById('player-cards');
    const dealerCardsDiv = document.getElementById('dealer-cards');
    const playerTotalDiv = document.getElementById('player-total');
    const dealerTotalDiv = document.getElementById('dealer-total');
    const actionIndicator = document.getElementById('action-indicator');
    const agentInfo = document.getElementById('agent-info');
    
    // Clear previous content
    playerCardsDiv.innerHTML = '';
    dealerCardsDiv.innerHTML = '';
    
    // Extract cards from trace
    const playerCards = [];
    const dealerCards = [];
    
    steps.forEach(step => {
        if (step.card !== null) {
            if (step.actor === 'PLAYER') {
                playerCards.push(step.card);
            } else if (step.actor === 'SYSTEM' || step.actor === 'DEALER') {
                dealerCards.push(step.card);
            }
        }
    });
    
    // Display player cards
    if (playerCards.length > 0) {
        playerCards.forEach(card => {
            const cardEl = document.createElement('div');
            cardEl.className = 'card';
            cardEl.innerHTML = cardEmojis[card] || '🃏';
            playerCardsDiv.appendChild(cardEl);
        });
    }
    
    // Display dealer cards
    if (dealerCards.length > 0) {
        dealerCards.forEach((card, index) => {
            const cardEl = document.createElement('div');
            cardEl.className = 'card';
            // First card is shown, second might be hidden in some traces
            cardEl.innerHTML = cardEmojis[card] || '🃏';
            dealerCardsDiv.appendChild(cardEl);
        });
    }
    
    // Update totals
    playerTotalDiv.innerHTML = `Total: <strong>${summary.player_total}</strong>`;
    dealerTotalDiv.innerHTML = `Total: <strong>${summary.dealer_total}</strong>`;
    
    // Update action indicator
    actionIndicator.innerHTML = '✓ Hand Complete';
    
    // Update agent info
    agentInfo.innerHTML = `<strong>Agent:</strong> ${summary.agent} | <strong>Dealer Upcard:</strong> ${cardEmojis[summary.dealer_upcard] || '?'}`;
}

// Display Cards
function displayCards(summary) {
    const playerTotal = summary.player_total;
    const dealerTotal = summary.dealer_total;
    
    const playerCardsDiv = document.getElementById('player-cards');
    const dealerCardsDiv = document.getElementById('dealer-cards');
    const playerTotalDiv = document.getElementById('player-total');
    const dealerTotalDiv = document.getElementById('dealer-total');
    
    // Clear previous cards
    playerCardsDiv.innerHTML = '';
    dealerCardsDiv.innerHTML = '';
    
    // This is simplified - in a real implementation, we'd track which cards were dealt
    // For now, we just show the totals
    playerTotalDiv.innerHTML = `Total: <strong>${playerTotal}</strong>`;
    dealerTotalDiv.innerHTML = `Total: <strong>${dealerTotal}</strong>`;
}

// Display Result
function displayResult(payoff, summary) {
    const resultBox = document.getElementById('result-box');
    
    let resultClass = '';
    let resultText = '';
    
    if (payoff === 1) {
        resultClass = 'win';
        resultText = '🎉 Player Wins!';
    } else if (payoff === -1) {
        resultClass = 'loss';
        if (summary.player_bust) {
            resultText = '💥 Player Busts - Dealer Wins!';
        } else if (summary.dealer_bust) {
            resultText = '🎯 Dealer Busts - Player Wins!';
        } else {
            resultText = '😞 Dealer Wins!';
        }
    } else {
        resultClass = 'push';
        resultText = '🤝 Push (Tie)!';
    }
    
    resultBox.className = `result-box ${resultClass}`;
    resultBox.innerHTML = `
        <div>${resultText}</div>
        <div style="margin-top: 10px; font-size: 0.9em;">
            Player: ${summary.player_total} | Dealer: ${summary.dealer_total}
        </div>
    `;
}

// Display Trace
function displayTrace(steps) {
    const traceDiv = document.getElementById('steps-trace');
    
    let html = '<h4>📝 Hand Trace</h4>';
    
    steps.forEach(step => {
        const card = step.card ? cardEmojis[step.card] || '🃏' : '';
        html += `
            <div class="step-item">
                <span class="step-actor">${step.actor}</span> 
                <span class="step-action">${step.action}</span> 
                ${card} | P:${step.player_total} D:${step.dealer_total}
                ${step.note ? `<span class="step-note">${step.note}</span>` : ''}
            </div>
        `;
    });
    
    traceDiv.innerHTML = html;
}

// Run Tournament
async function runTournament() {
    const numHands = parseInt(document.getElementById('hands-input').value) || 1000;
    const seed = document.getElementById('tournament-seed-input').value || null;
    const btn = document.getElementById('run-tournament-btn');
    const loading = document.getElementById('tournament-loading');
    const welcome = document.getElementById('tournament-welcome');
    const resultsDiv = document.getElementById('tournament-results');
    
    btn.disabled = true;
    loading.style.display = 'block';
    
    try {
        const response = await fetch('/api/match', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                num_hands: numHands,
                seed: seed ? parseInt(seed) : null
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            displayTournamentResults(data.results);
            welcome.style.display = 'none';
            resultsDiv.style.display = 'block';
        } else {
            alert('Error running tournament: ' + data.error);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to run tournament');
    } finally {
        btn.disabled = false;
        loading.style.display = 'none';
    }
}

// Display Tournament Results
function displayTournamentResults(results) {
    const grid = document.getElementById('results-grid');
    
    let html = '';
    
    ['A', 'B'].forEach(agent => {
        const stats = results[agent];
        const winRate = (stats.wins / stats.hands * 100).toFixed(1);
        
        html += `
            <div class="result-card">
                <h3>${stats.agent}</h3>
                <div class="result-stat">
                    <span class="result-stat-label">Total Hands:</span>
                    <span class="result-stat-value">${stats.hands}</span>
                </div>
                <div class="result-stat">
                    <span class="result-stat-label">Wins:</span>
                    <span class="result-stat-value">${stats.wins}</span>
                </div>
                <div class="result-stat">
                    <span class="result-stat-label">Losses:</span>
                    <span class="result-stat-value">${stats.losses}</span>
                </div>
                <div class="result-stat">
                    <span class="result-stat-label">Pushes:</span>
                    <span class="result-stat-value">${stats.pushes}</span>
                </div>
                <div class="result-stat">
                    <span class="result-stat-label">Win Rate:</span>
                    <span class="result-stat-value">${winRate}%</span>
                </div>
                <div class="result-stat">
                    <span class="result-stat-label">Avg Return:</span>
                    <span class="result-stat-value">${stats.avg_return.toFixed(4)}</span>
                </div>
            </div>
        `;
    });
    
    grid.innerHTML = html;
}
