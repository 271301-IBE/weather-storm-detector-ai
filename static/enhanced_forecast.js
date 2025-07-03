/**
 * Enhanced Weather Forecast JavaScript
 * Handles advanced forecast display with multiple prediction methods
 */

class EnhancedForecastManager {
    constructor() {
        this.currentMethod = 'ensemble';
        this.forecastData = {};
        this.accuracyData = {};
        this.comparisonData = {};
        this.refreshInterval = 300000; // 5 minutes
        this.refreshTimer = null;
        
        this.init();
    }
    
    init() {
        console.log('Initializing Enhanced Forecast Manager...');
        
        // Set up tab change handlers
        this.setupTabHandlers();
        
        // Load initial data
        this.loadAllForecastData();
        
        // Set up auto-refresh
        this.startAutoRefresh();
        
        // Set up error handling
        this.setupErrorHandling();
    }
    
    setupTabHandlers() {
        const tabs = document.querySelectorAll('#forecastTabs button[data-bs-toggle="tab"]');
        tabs.forEach(tab => {
            tab.addEventListener('shown.bs.tab', (event) => {
                const targetId = event.target.getAttribute('data-bs-target');
                const method = targetId.replace('#', '').replace('-pane', '');
                this.currentMethod = method;
                this.updateMethodDetails(method);
                console.log(`Switched to forecast method: ${method}`);
            });
        });
    }
    
    async loadAllForecastData() {
        console.log('Loading all forecast data...');
        
        try {
            // Show loading states
            this.showLoadingStates();
            
            // Load enhanced forecasts
            await this.loadEnhancedForecasts();
            
            // Load accuracy data
            await this.loadAccuracyData();
            
            // Load comparison data
            await this.loadComparisonData();
            
            // Update displays
            this.updateAllDisplays();
            
            console.log('All forecast data loaded successfully');
            
        } catch (error) {
            console.error('Error loading forecast data:', error);
            this.showError('Failed to load forecast data. Please try again.');
        }
    }
    
    async loadEnhancedForecasts() {
        try {
            const response = await fetch('/api/enhanced_forecast');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            this.forecastData = await response.json();
            console.log('Enhanced forecasts loaded:', this.forecastData);
            
        } catch (error) {
            console.error('Error loading enhanced forecasts:', error);
            throw error;
        }
    }
    
    async loadAccuracyData() {
        try {
            const response = await fetch('/api/forecast_accuracy');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            this.accuracyData = await response.json();
            console.log('Accuracy data loaded:', this.accuracyData);
            
        } catch (error) {
            console.error('Error loading accuracy data:', error);
            // Don't throw - accuracy data is optional
        }
    }
    
    async loadComparisonData() {
        try {
            const response = await fetch('/api/forecast_comparison');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            this.comparisonData = await response.json();
            console.log('Comparison data loaded:', this.comparisonData);
            
        } catch (error) {
            console.error('Error loading comparison data:', error);
            // Don't throw - comparison data is optional
        }
    }
    
    showLoadingStates() {
        const loadingHTML = '<tr><td colspan="9" class="text-center"><div class="spinner-border spinner-border-sm me-2"></div>Loading forecast...</td></tr>';
        
        document.getElementById('ensembleForecastBody').innerHTML = loadingHTML;
        document.getElementById('aiForecastBody').innerHTML = loadingHTML;
        document.getElementById('physicsForecastBody').innerHTML = loadingHTML;
        document.getElementById('comparisonForecastBody').innerHTML = '<tr><td colspan="10" class="text-center"><div class="spinner-border spinner-border-sm me-2"></div>Loading comparison...</td></tr>';
        
        // Update header badges
        document.getElementById('forecastMethod').textContent = 'Loading...';
        document.getElementById('forecastMethod').className = 'badge bg-secondary me-2';
        document.getElementById('forecastConfidence').textContent = 'Confidence: --';
        document.getElementById('forecastLastUpdated').textContent = 'Last updated: --';
    }
    
    updateAllDisplays() {
        // Update individual forecast tables
        this.updateForecastTable('ensemble', this.forecastData.ensemble);
        this.updateForecastTable('ai', this.forecastData.ai);
        this.updateForecastTable('physics', this.forecastData.physics);
        
        // Update comparison table
        this.updateComparisonTable();
        
        // Update header information
        this.updateHeaderInfo();
        
        // Update accuracy stats
        this.updateAccuracyStats();
        
        // Update method details for current tab
        this.updateMethodDetails(this.currentMethod);
    }
    
    updateForecastTable(method, forecastData) {
        const tableBodyId = `${method}ForecastBody`;
        const tableBody = document.getElementById(tableBodyId);
        
                if (!forecastData || !forecastData.forecast_data || forecastData.forecast_data.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">No forecast data available</td></tr>';
            return;
        }
        
        let html = '';
        forecastData.forecast_data.forEach(item => {
            const confidence = item.metadata ? item.metadata.confidence * 100 : 0;
            const confidenceClass = this.getConfidenceClass(confidence);
            const confidenceBadge = `<span class="badge bg-${confidenceClass}">${confidence.toFixed(0)}%</span>`;
            
            html += `
                <tr>
                    <td><strong>${this.formatTime(item.timestamp)}</strong></td>
                    <td>${item.temperature.toFixed(1)}°C</td>
                    <td>${item.humidity.toFixed(0)}%</td>
                    <td>${item.pressure.toFixed(0)}</td>
                    <td>${item.wind_speed.toFixed(1)}</td>
                    <td>${item.precipitation.toFixed(1)}</td>
                    <td>${item.precipitation_probability.toFixed(0)}%</td>
                    <td>
                        <span class="badge bg-light text-dark">${this.formatCondition(item.condition)}</span>
                    </td>
                    <td>${confidenceBadge}</td>
                </tr>
            `;
        });
        
        tableBody.innerHTML = html;
    }
    
    updateComparisonTable() {
        const tableBody = document.getElementById('comparisonForecastBody');
        
        if (!this.comparisonData.comparison_matrix || this.comparisonData.comparison_matrix.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">No comparison data available</td></tr>';
            return;
        }
        
        let html = '';
        this.comparisonData.comparison_matrix.forEach(hour => {
            html += `
                <tr>
                    <td><strong>${hour.time}</strong></td>
                    <td class="text-success">${hour.ensemble ? hour.ensemble.temperature : '--'}</td>
                    <td class="text-info">${hour.ai ? hour.ai.temperature : '--'}</td>
                    <td class="text-warning">${hour.physics ? hour.physics.temperature : '--'}</td>
                    <td class="text-success">${hour.ensemble ? hour.ensemble.humidity : '--'}</td>
                    <td class="text-info">${hour.ai ? hour.ai.humidity : '--'}</td>
                    <td class="text-warning">${hour.physics ? hour.physics.humidity : '--'}</td>
                    <td class="text-success">${hour.ensemble ? hour.ensemble.pressure : '--'}</td>
                    <td class="text-info">${hour.ai ? hour.ai.pressure : '--'}</td>
                    <td class="text-warning">${hour.physics ? hour.physics.pressure : '--'}</td>
                </tr>
            `;
        });
        
        tableBody.innerHTML = html;
    }
    
    updateHeaderInfo() {
        // Determine best forecast to show in header
                let bestForecast = this.forecastData.ensemble || this.forecastData.ai || this.forecastData.physics;
        
        if (bestForecast && bestForecast.metadata) {
            const method = bestForecast.metadata.primary_method || 'unknown';
            const confidence = bestForecast.metadata.confidence ? 
                bestForecast.metadata.confidence * 100 : 0;
            
            // Update method badge
            const methodBadge = document.getElementById('forecastMethod');
            methodBadge.textContent = this.getMethodDisplayName(method);
            methodBadge.className = `badge bg-${this.getMethodColor(method)} me-2`;
            
            // Update confidence badge
            const confidenceBadge = document.getElementById('forecastConfidence');
            const confidenceClass = this.getConfidenceClass(confidence);
            confidenceBadge.textContent = `Confidence: ${confidence.toFixed(0)}%`;
            confidenceBadge.className = `badge bg-${confidenceClass}`;
            
            // Update last updated
            document.getElementById('forecastLastUpdated').textContent = 
                `Last updated: ${this.formatTimestamp(bestForecast.timestamp)}`;
        }
    }
    
    updateMethodDetails(method) {
        const detailsContainer = document.getElementById('methodDetails');
        let methodData = null;
        let detailsHTML = '';
        
        switch(method) {
            case 'ensemble':
                methodData = this.forecastData.ensemble;
                detailsHTML = this.generateEnsembleDetails(methodData);
                break;
            case 'ai':
                methodData = this.forecastData.ai;
                detailsHTML = this.generateAIDetails(methodData);
                break;
            case 'physics':
                methodData = this.forecastData.physics;
                detailsHTML = this.generatePhysicsDetails(methodData);
                break;
            case 'comparison':
                detailsHTML = this.generateComparisonDetails();
                break;
            default:
                detailsHTML = '<small class="text-muted">Select a forecast method to see details</small>';
        }
        
        detailsContainer.innerHTML = detailsHTML;
    }
    
    generateEnsembleDetails(data) {
                if (!data || !data.metadata) return '<small class="text-danger">Ensemble forecast not available</small>';
        
        const weights = data.metadata.ensemble_weights || {};
        let html = `
            <small>
                <strong>🎯 Ensemble Method:</strong><br>
                <span class="text-muted">Combines multiple forecasting approaches:</span><br>
        `;
        
        Object.entries(weights).forEach(([method, weight]) => {
            const percentage = (weight * 100).toFixed(0);
            html += `• ${this.getMethodDisplayName(method)}: ${percentage}%<br>`;
        });
        
        html += `
                <span class="text-muted">Data sources: ${data.data_sources ? data.data_sources.length : 0}</span>
            </small>
        `;
        
        return html;
    }
    
    generateAIDetails(data) {
        if (!data) return '<small class="text-danger">AI forecast not available</small>';
        
        return `
            <small>
                <strong>🤖 AI Prediction:</strong><br>
                <span class="text-muted">DeepSeek Chat API analysis</span><br>
                • Model: deepseek-chat<br>
                • Temperature: 0.1 (precise)<br>
                • Considers: atmospheric patterns, historical data<br>
                • Update frequency: Every 30 minutes<br>
                <span class="text-muted">Data sources: ${data.data_sources ? data.data_sources.length : 0}</span>
            </small>
        `;
    }
    
    generatePhysicsDetails(data) {
        if (!data) return '<small class="text-danger">Physics forecast not available</small>';
        
        return `
            <small>
                <strong>🧮 Local Physics:</strong><br>
                <span class="text-muted">Atmospheric physics calculations</span><br>
                • Pressure tendency analysis<br>
                • Diurnal temperature cycles<br>
                • Polynomial trend fitting<br>
                • Clausius-Clapeyron relations<br>
                <span class="text-muted">Data sources: ${data.data_sources ? data.data_sources.length : 0}</span>
            </small>
        `;
    }
    
    generateComparisonDetails() {
        return `
            <small>
                <strong>📊 Method Comparison:</strong><br>
                <span class="text-muted">Side-by-side analysis</span><br>
                • <span class="text-success">Ensemble:</span> Best overall accuracy<br>
                • <span class="text-info">AI:</span> Pattern recognition<br>
                • <span class="text-warning">Physics:</span> Mathematical consistency<br>
                <span class="text-muted">Use for method validation</span>
            </small>
        `;
    }
    
    updateAccuracyStats() {
        const statsContainer = document.getElementById('accuracyStats');
        
        if (!this.accuracyData.accuracy_stats) {
            statsContainer.innerHTML = '<small class="text-muted">Accuracy data not yet available</small>';
            return;
        }
        
        let html = '<small>';
        Object.entries(this.accuracyData.accuracy_stats).forEach(([method, stats]) => {
            if (stats.temperature) {
                const accuracy = stats.temperature.accuracy_score;
                const accuracyClass = accuracy > 80 ? 'success' : accuracy > 60 ? 'warning' : 'danger';
                html += `
                    <span class="badge bg-${accuracyClass} me-1">
                        ${this.getMethodDisplayName(method)}: ${accuracy.toFixed(0)}%
                    </span><br>
                `;
            }
        });
        html += `<span class="text-muted">Last 30 days</span></small>`;
        
        statsContainer.innerHTML = html;
    }
    
    // Utility methods
    
    formatTime(timestamp) {
        return new Date(timestamp).toLocaleTimeString('cs-CZ', { 
            hour: '2-digit', 
            minute: '2-digit' 
        });
    }
    
    formatTimestamp(timestamp) {
        return new Date(timestamp).toLocaleString('cs-CZ', { 
            hour: '2-digit', 
            minute: '2-digit',
            second: '2-digit'
        });
    }
    
    formatCondition(condition) {
        const conditionMap = {
            'clear': '☀️ Clear',
            'clouds': '☁️ Cloudy',
            'rain': '🌧️ Rain',
            'thunderstorm': '⛈️ Storm',
            'snow': '❄️ Snow',
            'drizzle': '🌦️ Drizzle',
            'mist': '🌫️ Mist',
            'fog': '🌫️ Fog'
        };
        return conditionMap[condition] || condition;
    }
    
    getConfidenceClass(confidence) {
        if (confidence >= 80) return 'success';
        if (confidence >= 60) return 'warning';
        if (confidence >= 40) return 'info';
        return 'danger';
    }
    
    getMethodColor(method) {
        const colorMap = {
            'ensemble': 'success',
            'ai_deepseek': 'info',
            'local_physics': 'warning',
            'local_ml': 'secondary'
        };
        return colorMap[method] || 'primary';
    }
    
    getMethodDisplayName(method) {
        const nameMap = {
            'ensemble': 'Ensemble',
            'ai_deepseek': 'AI DeepSeek',
            'ai': 'AI',
            'local_physics': 'Physics',
            'physics': 'Physics',
            'local_ml': 'ML',
            'ml': 'ML'
        };
        return nameMap[method] || method;
    }
    
    setupErrorHandling() {
        window.addEventListener('unhandledrejection', (event) => {
            console.error('Unhandled promise rejection in forecast manager:', event.reason);
            this.showError('An unexpected error occurred while loading forecast data.');
        });
    }
    
    showError(message) {
        console.error('Forecast error:', message);
        
        // Show error in all forecast bodies
        const errorHTML = `<tr><td colspan="9" class="text-center text-danger">⚠️ ${message}</td></tr>`;
        document.getElementById('ensembleForecastBody').innerHTML = errorHTML;
        document.getElementById('aiForecastBody').innerHTML = errorHTML;
        document.getElementById('physicsForecastBody').innerHTML = errorHTML;
        
        // Update header to show error
        document.getElementById('forecastMethod').textContent = 'Error';
        document.getElementById('forecastMethod').className = 'badge bg-danger me-2';
    }
    
    startAutoRefresh() {
        this.refreshTimer = setInterval(() => {
            console.log('Auto-refreshing forecast data...');
            this.loadAllForecastData();
        }, this.refreshInterval);
        
        console.log(`Auto-refresh enabled: every ${this.refreshInterval / 1000} seconds`);
    }
    
    stopAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
            console.log('Auto-refresh disabled');
        }
    }
    
    // Public methods for manual control
    
    refresh() {
        console.log('Manual refresh triggered');
        this.loadAllForecastData();
    }
    
    switchToMethod(method) {
        const tabButton = document.getElementById(`${method}-tab`);
        if (tabButton) {
            tabButton.click();
        }
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing Enhanced Forecast Manager...');
    window.enhancedForecastManager = new EnhancedForecastManager();
});

// Export for potential external use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = EnhancedForecastManager;
}