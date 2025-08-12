document.addEventListener('DOMContentLoaded', function () {
    loadEnhancedForecast();
    setInterval(loadEnhancedForecast, 60000); // Refresh every minute
});

function loadEnhancedForecast() {
    fetch('/api/enhanced_forecast')
        .then(response => response.json())
        .then(data => {
            updateForecastDisplay('ensemble', data.ensemble);
            updateForecastDisplay('ai', data.ai);
            updateForecastDisplay('physics', data.physics);
            updateComparisonTable(data);
        })
        .catch(error => console.error('Error loading enhanced forecast:', error));
}

function updateForecastDisplay(method, forecastData) {
    const forecastBody = document.getElementById(`${method}ForecastBody`);
    if (!forecastBody) return;

    if (forecastData && forecastData.forecast && forecastData.forecast.length > 0) {
        let tableContent = '';
        forecastData.forecast.forEach(item => {
            tableContent += `
                <tr>
                    <td class="nowrap"><strong>${item.hour}:00</strong></td>
                    <td class="text-end">${item.temperature}°C</td>
                    <td class="text-end">${item.humidity}%</td>
                    <td class="text-end">${item.pressure} hPa</td>
                    <td class="text-end">${item.wind_speed} m/s</td>
                    <td class="text-end">${item.precipitation} mm</td>
                    <td class="text-end">${item.precipitation_probability}%</td>
                    <td class="nowrap"><span class="badge bg-light text-dark">${item.condition}</span></td>
                    <td class="text-end"><span class="badge bg-success">${item.confidence}%</span> <span class="badge bg-secondary">${item.confidence_level}</span></td>
                </tr>
            `;
        });
        forecastBody.innerHTML = tableContent;

        // Update header
        if (method === 'ensemble') {
            document.getElementById('forecastMethod').textContent = forecastData.method;
            document.getElementById('forecastConfidence').textContent = `Confidence: ${forecastData.confidence}%`;
            document.getElementById('forecastLastUpdated').textContent = `Last updated: ${new Date(forecastData.generated_at).toLocaleTimeString()}`;
        }
    } else {
        forecastBody.innerHTML = '<tr><td colspan="9" class="text-center">No forecast data available</td></tr>';
    }
}

function updateComparisonTable(data) {
    const comparisonBody = document.getElementById('comparisonForecastBody');
    if (!comparisonBody) return;

    if (data.ensemble && data.ensemble.forecast && data.ensemble.forecast.length > 0) {
        let tableContent = '';
        for (let i = 0; i < data.ensemble.forecast.length; i++) {
            const ensemble = data.ensemble.forecast[i];
            const ai = data.ai && data.ai.forecast ? data.ai.forecast[i] : null;
            const physics = data.physics && data.physics.forecast ? data.physics.forecast[i] : null;

            tableContent += `
                <tr>
                    <td class="nowrap"><strong>${ensemble.hour}:00</strong></td>
                    <td class="text-end text-success">${ensemble ? ensemble.temperature : '--'}</td>
                    <td class="text-end text-info">${ai ? ai.temperature : '--'}</td>
                    <td class="text-end text-warning">${physics ? physics.temperature : '--'}</td>
                    <td class="text-end text-success">${ensemble ? ensemble.humidity : '--'}</td>
                    <td class="text-end text-info">${ai ? ai.humidity : '--'}</td>
                    <td class="text-end text-warning">${physics ? physics.humidity : '--'}</td>
                    <td class="text-end text-success">${ensemble ? ensemble.pressure : '--'}</td>
                    <td class="text-end text-info">${ai ? ai.pressure : '--'}</td>
                    <td class="text-end text-warning">${physics ? physics.pressure : '--'}</td>
                </tr>
            `;
        }
        comparisonBody.innerHTML = tableContent;
    } else {
        comparisonBody.innerHTML = '<tr><td colspan="10" class="text-center">No comparison data available</td></tr>';
    }
}
