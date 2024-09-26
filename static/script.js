const sendBtn = document.querySelector('#send-btn');
const promptInput = document.querySelector('#prompt-input');
const chatHistory = document.querySelector('#chat-history .card-body');
const csvInput = document.getElementById('csv-file-input'); // Ensure csvInput is defined
const fileFeedback = document.getElementById('file-preview'); // Placeholder for feedback/errors
let csvData = null; // To store parsed CSV data
const toggleButton = document.getElementById('toggle-button');
const dataPreview = document.getElementById('data-preview'); // Placeholder for data preview
const buttonContainer = document.querySelector('.button-container');
const modal = document.getElementById('popup-modal');
const closeModal = document.getElementById('close-modal');
const fileUploadArea = document.getElementById('file-upload-area');
const fileInput = document.getElementById('csv-file-input');

promptInput.addEventListener('input', function(event) {
    sendBtn.disabled = !event.target.value;
});

function appendMessage(content, className) {
    const messageElement = document.createElement('div');
    messageElement.className = `message ${className}`;
    messageElement.textContent = content;

    console.log('Appending message:', content);

    chatHistory.appendChild(messageElement);

    // Call autoscroll after appending the message
    chatHistory.scrollTop = chatHistory.scrollHeight; // Scroll to bottom
}


async function sendMessage() {
    const prompt = promptInput.value;
    if (!prompt) return;

    // Append user message
    appendMessage(prompt, 'user-message');

    // Clear input
    promptInput.value = '';
    sendBtn.disabled = true;

    // Check if CSV data has been uploaded
    if (!csvData) {
        appendMessage("Please upload a dataset first.", 'bot-message');
        return; // Stop execution if no dataset is uploaded
    }

    try {
        const response = await fetch('http://127.0.0.1:8000/query', {
            method: 'POST',
            body: JSON.stringify({ prompt }),
            headers: {
                'Content-Type': 'application/json'
            }
        });

        // Check if the response status is OK (status code 200)
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || "Something went wrong");
        }

        const data = await response.json();
        console.log('Response from server:', data);

        
        // Check if data.response is a valid Vega-Lite spec
        if (data && data.specification && data.specification.$schema) { 
            // No need to create a separate div here, `renderChart` will handle it
    
            // Render the chart
            renderChart(data.specification);
    
            // Append the description below the chart if it exists
            if (data.description) {
                appendMessage(data.description, 'bot-message');
            }
        } else {
            appendMessage(data.response || "No valid response received", 'bot-message');
            console.error("No valid Vega-Lite spec returned in response.");
        }

    } catch (error) {
        console.error('Error:', error);
        appendMessage("Error: " + error.message, 'bot-message'); // Display the error message in the chat
    }
}

promptInput.addEventListener('keyup', function(event) {
    if (event.keyCode === 13) {
        sendMessage();
    }
});

sendBtn.addEventListener('click', sendMessage);

// Function to open the modal with a custom message
function openModal(message) {
    document.getElementById('modal-message').textContent = message;
    modal.style.display = 'block'; // Show the modal
}

// Function to close the modal
closeModal.addEventListener('click', function() {
    modal.style.display = 'none'; // Hide the modal
});

// Close modal when clicking anywhere outside of it
window.addEventListener('click', function(event) {
    if (event.target === modal) {
        modal.style.display = 'none'; // Hide the modal
    }
});

csvInput.addEventListener('change', async function(event) {
    const file = event.target.files[0];
    
    if (!file || !file.name.endsWith('.csv')) {
        openModal('Please upload a valid CSV file.');
        csvData = null; // Clear old CSV data
        return;
    }

    fileFeedback.textContent = ''; // Clear any error message

    // Clear previous data preview before uploading new CSV
    dataPreview.innerHTML = ''; // Clear previous preview
    csvData = null; // Reset csvData to ensure old data is cleared

    // Prepare form data
    const formData = new FormData();
    formData.append('csv_file', file);

    try {
        // Send the CSV to the backend
        const response = await fetch('http://localhost:8000/upload_csv', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.message) {
            fileFeedback.textContent = data.message;  // Show success message
        }

        // Read and preview the CSV using FileReader
        const reader = new FileReader();
        reader.onload = function(event) {
            const csvContent = event.target.result;
            csvData = d3.csvParse(csvContent, d3.autoType); // Parse CSV and auto-detect types
        
            // Prepare the table HTML and display it
            dataPreview.innerHTML = generateTablePreview(csvData);
            dataPreview.style.display = 'block'; 

            // Show the toggle button
            buttonContainer.style.display = 'flex';
            buttonContainer.style.justifyContent = 'center';
        };

        reader.readAsText(file);

    } catch (error) {
        fileFeedback.textContent = 'Error uploading CSV.';
        console.error('Error:', error);
    }
});


toggleButton.addEventListener('click', () => {
    if (dataPreview.style.display === 'none') {
        dataPreview.style.display = 'block';  // Show the table
        toggleButton.textContent = 'Hide Table Preview';
    } else {
        dataPreview.style.display = 'none';  // Hide the table
        toggleButton.textContent = 'Show Table Preview';
    }
});

// Generate a table preview of the CSV data
function generateTablePreview(data) {
    const previewLimit = 5; // Limit rows displayed in preview
    const keys = Object.keys(data[0]); // Get column names

    let table = '<table class="table table-sm table-bordered">';
    table += '<thead><tr>';
    
    keys.forEach(key => {
        table += `<th>${key}</th>`;
    });

    table += '</tr></thead><tbody>';

    data.slice(0, previewLimit).forEach(row => {
        table += '<tr>';
        keys.forEach(key => {
            table += `<td>${row[key]}</td>`;
        });
        table += '</tr>';
    });

    table += '</tbody></table>';
    return table;
}

// Function to render the Vega-Lite chart
function renderChart(vegaLiteSpec) {
    // Create a new chart container for each message
    const chartContainer = document.createElement('div');
    chartContainer.classList.add('chart-container', 'mt-3'); // Add necessary classes

    // Find the chat history container where bot messages go
    const chatHistory = document.querySelector('#chat-history .card-body');

    // Append a new bot message div for the chart
    const botMessageDiv = document.createElement('div');
    botMessageDiv.classList.add('bot-message');

    // Create a new div inside botMessageDiv for the chart
    const chartDiv = document.createElement('div');
    botMessageDiv.appendChild(chartDiv);
    
    // Append bot message (with the chart div) to the chat history
    chatHistory.appendChild(botMessageDiv);

    // Use Vega-Lite to render the chart
    vegaEmbed(chartDiv, vegaLiteSpec)
        .then(result => {
            console.log("Chart rendered successfully");
            // Call autoscroll after rendering the chart
            chatHistory.scrollTop = chatHistory.scrollHeight; // Scroll to bottom
        })
        .catch(error => {
            console.error("Error rendering chart:", error);
        });
}

