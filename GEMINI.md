# Gemini Code Assistant Context

## Project Overview

This project is a comprehensive weather monitoring and storm detection system for the Czech Republic, specifically designed for the Brno/Reckovice area in South Moravia. It is a Python-based application that utilizes a variety of APIs to collect weather data, which is then analyzed by an AI to predict storms. The system is designed to be deployed on a Raspberry Pi and includes a Flask-based web interface for data visualization and system monitoring.

### Key Technologies

*   **Backend:** Python, Flask
*   **Frontend:** HTML, CSS, JavaScript
*   **Database:** SQLite
*   **AI:** DeepSeek API
*   **Weather Data APIs:** OpenWeather, Visual Crossing, Tomorrow.io
*   **Deployment:** Raspberry Pi (via systemd service)

### Core Features

*   **Real-time Weather Monitoring:** Fetches data from multiple APIs every 10 minutes.
*   **AI-Powered Storm Detection:** Uses the DeepSeek AI for high-accuracy thunderstorm prediction.
*   **Smart Email Alerts:** Sends notifications for high-confidence storm detections.
*   **Detailed PDF Reports:** Generates comprehensive weather analysis reports.
*   **Web Dashboard:** A Flask-based web application provides a user interface for monitoring weather data, AI analysis, and system status.
*   **Lightning Detection:** Integrates with Blitzortung.org for real-time lightning data.

## Building and Running

The project is primarily run using shell scripts that handle environment setup, process management, and execution of the main Python scripts.

### Setup

To set up the project, run the `setup.sh` script. This will create a Python virtual environment, install the required dependencies from `requirements.txt`, and create a `.env` file for configuration.

```bash
./setup.sh
```

### Running the System

The main application can be started using the `run_all.sh` script. This script starts the main weather monitoring system, the web interface, and the thunderstorm predictor in the background.

```bash
./run_all.sh
```

To run the main monitoring system in the foreground for debugging, you can use the `start.sh` script or run the `main.py` script directly.

```bash
./start.sh
# OR
python main.py
```

The web application can be started independently for development or testing:

```bash
python web_app.py
```

### Stopping the System

To stop all running processes, use the `stop_all.sh` script.

```bash
./stop_all.sh
```

To stop only the main monitoring system, use the `stop.sh` script.

```bash
./stop.sh
```

## Development Conventions

*   **Configuration:** All configuration is managed through environment variables, which are loaded from a `.env` file. The `config.py` module defines the data classes for the configuration.
*   **Asynchronous Operations:** The project uses `asyncio` for handling asynchronous tasks, such as fetching data from APIs.
*   **Modularity:** The project is well-structured, with different modules for data fetching, AI analysis, email notifications, and other functionalities.
*   **Web Interface:** The web interface is built with Flask and provides a simple dashboard for monitoring the system. It includes API endpoints for fetching data and a basic authentication system.
*   **Testing:** The project includes a number of test files (e.g., `test_system.py`, `test_combined_system.py`), which suggests that testing is an important part of the development process.
