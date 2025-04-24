// Initialize Supabase client
require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });
const SUPABASE_URL = process.env.SUPABASE_URL; 
const SUPABASE_KEY = process.env.SUPABASE_KEY; 
const PORT = process.env.PORT;
const SERVER_URL = process.env.SERVER_URL;

const spb = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);

const API_URL = `http://${SERVER_URL}:${PORT}/`;

let chart, barChart;
let banks = ["HDFC", "ICICI", "SBI", "KOTAK"];
let bankRates = [];

// Function to send a message
async function sendMessage() {
    let inputField = document.getElementById("chatInput");
    let message = inputField.value.trim();

    if (!message) return;

    let chatBox = document.getElementById("chatBox");
    chatBox.innerHTML += `<div class="chat-message user">You: ${message}</div>`;
    chatBox.scrollTop = chatBox.scrollHeight;
    inputField.value = ""; 

    try {

        const payload = {
            text : message,
        };

        let response = await fetch(API_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        let data = await response.json();
        chatBox.innerHTML += `<div class="chat-message bot" markdown="1">Server: ${marked.parse(data.message)}</div>`;
        chatBox.scrollTop = chatBox.scrollHeight;
    } catch (error) {
        console.error("Error sending message:", error);
        chatBox.innerHTML += `<div class="chat-message bot" markdown="1">Server Error. Try again.</div>`;
    }
}

// Speech-to-Text function
function startSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        alert("Speech Recognition is not supported in your browser.");
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => {
        console.log("Speech recognition started...");
    };

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        console.log("Transcript:", transcript);
        document.getElementById("chatInput").value = transcript;
    };

    recognition.onerror = (event) => {
        console.error("Speech recognition error:", event.error);
        alert("Speech recognition error: " + event.error);
    };

    recognition.onspeechend = () => {
        recognition.stop();
        console.log("Speech recognition ended.");
    };

    recognition.start();
}
// Fetch interest rates from Supabase
async function fetchRates(duration) {
    let rates = [];
    for (let bank of banks) {
        const { data, error } = await spb
            .from(bank)
            .select('rate')
            .lte("tenure_start", duration)
            .gte("tenure_end", duration)
            .limit(1);

        if (error) {
            console.error(`Error fetching data for ${bank}:`, error);
        } else {
            rates.push({ bank, rate: data?.[0]?.rate || 0 });
        }
    }
    return rates;
}

async function updateChart() {
    let principal = parseFloat(document.getElementById('principal').value);
    let years = parseInt(document.getElementById('years').value);
    let months = parseInt(document.getElementById('months').value);
    let days = parseInt(document.getElementById('days').value);

    let tenureDays = (years * 365) + (months * 30) + days;

    bankRates = await fetchRates(tenureDays);
    generateFDChart(principal, bankRates, tenureDays);
    generateBarChart(bankRates);
}
updateChart()


// Generate Bar Chart for interest rates
function generateBarChart(bankRates) {
    let ctx = document.getElementById('barChart').getContext('2d');
    if (barChart) barChart.destroy();

    barChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: bankRates.map(({ bank }) => bank),
            datasets: [{
                label: 'FD Interest Rate (%)',
                data: bankRates.map(({ rate }) => rate),
                backgroundColor: ['blue', 'red', 'green', 'purple']
            }]
        },
        options: {
            responsive: true,
            scales: { y: { beginAtZero: true } }
        }
    });

    let bestBank = bankRates.reduce((prev, curr) => (prev.rate > curr.rate ? prev : curr), { rate: 0 });
    document.getElementById('bestRate').innerText = `Best Rate: ${bestBank.bank} at ${bestBank.rate}%`;
}

// Generate FD Growth Chart
function generateFDChart(principal, bankRates, tenureDays) {
    let labels = [];
    let datasets = [];
    let n = 4; // Quarterly compounding
    let tenureYears = tenureDays / 365;
    let tenureMonths = tenureDays / 30;
    let colors = ['blue', 'red', 'green', 'purple'];

    const ctx = document.getElementById('fdChart').getContext('2d');
    if (chart) chart.destroy();
    chart = new Chart(ctx, {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { title: { display: true, text: 'Tenure' } },
                y: { title: { display: true, text: 'Amount' } }
            },
            plugins: {
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function(tooltipItem) {
                            let { bank, rate } = bankRates[tooltipItem.datasetIndex];
                            return `${bank} - ${rate}% : ₹${tooltipItem.raw}`;
                        }
                    }
                }
            },
            hover: {
                mode: 'index',
                intersect: false
            },
            onHover: function(event, chartElements) {
                if (chartElements.length) {
                    let maturityValues = bankRates.map(({ bank, rate }) => {
                        return {
                            bank,
                            rate,
                            maturity: principal * Math.pow(1 + rate / (n * 100), n * tenureYears)
                        };
                    });

                    maturityValues.sort((a, b) => b.maturity - a.maturity);
                    let highest = maturityValues[0];

                    let totalInterest = highest.maturity - principal;
                    document.getElementById('maturityAmount').innerText = `${highest.bank} Maturity Amount: ₹${highest.maturity.toFixed(2)}`;
                    document.getElementById('interestAmount').innerText = `${highest.bank} Total Interest: ₹${totalInterest.toFixed(2)}`;
                }
            }
        }
    });

    bankRates.forEach(({ bank, rate }, index) => {
        let values = [];
        if (tenureDays <= 30) {
            for (let t = 0; t <= tenureDays; t++) {
                let amount = principal * Math.pow(1 + rate / (n * 100), n * (t / 365));
                if (index === 0) labels.push(t + " days");
                values.push(amount.toFixed(2));
            }
        } else if (tenureDays <= 730) {
            for (let t = 0; t <= tenureMonths; t++) {
                let amount = principal * Math.pow(1 + rate / (n * 100), n * (t / 12));
                if (index === 0) labels.push(t + " months");
                values.push(amount.toFixed(2));
            }
        } else {
            for (let t = 0; t <= tenureYears; t++) {
                let amount = principal * Math.pow(1 + rate / (n * 100), n * t);
                if (index === 0) labels.push(t + " years");
                values.push(amount.toFixed(2));
            }
        }

        chart.data.labels = labels;
        chart.data.datasets.push({
            label: `${bank} - ${rate}%`,
            data: values,
            borderColor: colors[index % colors.length],
            borderWidth: 3,
            fill: false,
            pointRadius: 5,
            pointHoverRadius: 8
        });
    });

    chart.update();
}
