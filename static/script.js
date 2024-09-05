const sendBtn = document.querySelector('#send-btn');
const promptInput = document.querySelector('#prompt-input');
const chatHistory = document.querySelector('#chat-history .card-body');

promptInput.addEventListener('input', function(event) {
    sendBtn.disabled = !event.target.value;
});

function appendMessage(content, className) {
    const messageElement = document.createElement('div');
    messageElement.className = `message ${className}`;
    messageElement.textContent = content;

    console.log('Appending message:', content);

    chatHistory.appendChild(messageElement);
    chatHistory.scrollTop = chatHistory.scrollHeight; // Scroll to bottom
}

function sendMessage() {
    const prompt = promptInput.value;
    if (!prompt) return;

    // Append user message
    appendMessage(prompt, 'user-message');

    // Clear input
    promptInput.value = '';
    sendBtn.disabled = true;

    fetch('http://localhost:8000/query', {
        method: 'POST',
        body: JSON.stringify({ prompt }),
        headers: {
        'Content-Type': 'application/json'
        }
    }).then(response => response.json())
    .then(data => {   
        console.log('Response from server:', data); 
        setTimeout(() => {
            appendMessage(data.response, 'bot-message');
        }, 300); 
    }).catch(error => {
        console.error('Error:', error); 
    });
}

promptInput.addEventListener('keyup', function(event) {
    if (event.keyCode === 13) {
        sendMessage();
    }
});

sendBtn.addEventListener('click', sendMessage);