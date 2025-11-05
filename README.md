# IoT and Energy Analytics Platform

A comprehensive IoT management and energy analytics platform built with Django, featuring real-time device monitoring, data analytics, and automated event management.

## Features

### Device Management
- **Device Registration & Configuration**: Create and manage IoT devices with custom types and properties
- **Real-time Monitoring**: Track device status, heartbeats, and live data streams via WebSockets
- **Device Search & Filtering**: Advanced search capabilities with pagination support
- **Favorite Devices**: Mark and organize frequently accessed devices
- **Device Geolocation**: GPS-based device tracking with latitude/longitude support
- **OTA Updates**: Over-the-air firmware and configuration updates for devices

### Data Collection & Analytics
- **Real-time Data Ingestion**: MQTT-based data collection from IoT devices
- **Time-series Analytics**: High-performance queries using ClickHouse database
- **Historical Data Reports**: Generate and export device data reports
- **Dynamic Dashboards**: Customizable widgets for energy consumption, generation, and device metrics
- **Apache Superset Integration**: Advanced data visualization and business intelligence

### Event Management & Automation
- **Event-based Triggers**: Define custom events based on device data thresholds
- **Scheduled Events**: Cron-based event scheduling for automated actions
- **Action Execution**: Trigger device commands based on event conditions
- **Multi-channel Notifications**: Email and mobile notifications for critical events
- **Event History**: Track and analyze past event occurrences

### Energy Analytics
- **Energy Consumption Tracking**: Monitor daily energy usage across devices
- **Energy Generation Monitoring**: Track solar or renewable energy generation
- **Import/Export Analysis**: Analyze energy import and export metrics
- **Load Detection**: Machine learning-based appliance load detection
- **Profit Calculation**: Calculate energy savings and profit metrics

### Document Management
- **Device Documentation**: Upload and manage documents associated with devices
- **User Documents**: Personal document storage and organization
- **Multi-format Support**: Handle various document types and formats

### User Management & Authentication
- **User Registration & Authentication**: Token-based authentication with JWT
- **Role-based Access Control**: Granular permissions for device access
- **User Profiles**: Customizable user profiles with avatar support
- **Social Authentication**: Integration with social login providers

### Communication
- **WebSocket Support**: Real-time bidirectional communication with devices
- **MQTT Broker Integration**: Standard IoT protocol support for device communication
- **REST API**: Comprehensive RESTful API for all operations
- **Telegram Bot Integration**: Device control and notifications via Telegram

## Tech Stack

### Backend
- **Framework**: Django 4.0.9
- **API**: Django REST Framework 3.14.0
- **Async Support**: Daphne 4.0.0 (ASGI server)
- **Task Queue**: Celery with django-celery-beat 2.4.0
- **WebSockets**: Django Channels with channels-redis 4.0.0

### Databases
- **Primary Database**: MongoDB (via djongo 1.3.6)
- **Analytics Database**: ClickHouse (via django-clickhouse 1.2.1)
- **Cache & Message Broker**: Redis 6.2

### Data Processing & ML
- **Machine Learning**: scikit-learn
- **Data Processing**: pandas, numpy (implied via sklearn)
- **Time Series**: Custom analytics with ClickHouse

### Communication Protocols
- **MQTT**: paho-mqtt 1.6.1
- **WebSockets**: Django Channels
- **HTTP/REST**: Django REST Framework

### Additional Libraries
- **API Documentation**: drf-yasg 1.21.4 (Swagger/OpenAPI)
- **Schema Validation**: jsonschema 4.17.0
- **Authentication**: dj-rest-auth 2.2.5
- **CORS**: django-cors-headers 3.13.0
- **Geolocation**: timezonefinder 6.1.6
- **Monitoring**: sentry-sdk 1.11.1
- **Telegram**: python-telegram-bot 13.11
- **Data Formats**: PyYAML 6.0, simplejson 3.17.6

### DevOps & Deployment
- **Containerization**: Docker & Docker Compose
- **Process Management**: Supervisor
- **Python Version**: 3.11

## Getting Started

### Prerequisites
- Docker (v20.10 or higher)
- Docker Compose (v2.0 or higher)
- Git

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/vkylamba/IoT-Management.git
cd IoT-Management
```

2. **Configure environment variables**
```bash
cd src/iot_server
cp env.template .env
```

Edit the `.env` file with your configuration:
```env
DJANGO_SECRET_KEY=your_secret_key_here
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8113
```

3. **Build and start the services**
```bash
cd ../..
docker-compose up --build
```

This will start the following services:
- **Application Server**: http://localhost:8113
- **MongoDB**: localhost:27017
- **Mongo Express** (DB Admin): http://localhost:8081
- **ClickHouse**: localhost:8123
- **Redis**: localhost:6379

4. **Initialize the database**

In a new terminal, run:
```bash
docker-compose exec app python manage.py migrate
docker-compose exec app python manage.py createsuperuser
```

5. **Access the application**
- API: http://localhost:8113/
- Swagger API Documentation: http://localhost:8113/swagger/
- Admin Panel: http://localhost:8113/admin/

### Running Locally (Development)

For local development without Docker:

1. **Install Python dependencies**
```bash
cd src
pip install -r requirements.txt
```

2. **Set up databases**
- Install and start MongoDB
- Install and start ClickHouse
- Install and start Redis

3. **Configure environment**
```bash
cd iot_server
cp env.template .env
# Edit .env with your local database credentials
```

4. **Run migrations**
```bash
python manage.py migrate
python manage.py migrate_clickhouse
```

5. **Start the development server**
```bash
python manage.py runserver 0.0.0.0:8000
```

6. **Start Celery worker (in separate terminal)**
```bash
celery -A iot_server worker -l info
```

7. **Start Celery beat (in separate terminal)**
```bash
celery -A iot_server beat -l info
```

8. **Start MQTT listener (in separate terminal)**
```bash
python manage.py mqtt
```

### API Usage

After starting the server, explore the API documentation at:
- **Swagger UI**: http://localhost:8113/swagger/
- **ReDoc**: http://localhost:8113/redoc/

**Example API calls:**

```bash
# Register a new user
curl -X POST http://localhost:8113/api-token-auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "password123", "email": "test@example.com"}'

# Login and get token
curl -X POST http://localhost:8113/api-token-auth/ \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "password123"}'

# Get devices (requires token)
curl -X GET http://localhost:8113/devices/ \
  -H "Authorization: Token YOUR_TOKEN_HERE"
```

## Project Structure

```
IoT-Management/
├── src/
│   ├── api/                    # REST API endpoints
│   ├── dashboard/              # Dashboard and widgets
│   ├── device/                 # Device management
│   ├── device_schemas/         # Device type schemas
│   ├── event/                  # Event management
│   ├── notification/           # Notification system
│   ├── datascience/            # ML models and data processing
│   ├── utils/                  # Utility functions
│   └── iot_server/             # Django settings
├── config/                     # Configuration files
├── docker-compose.yaml         # Docker services
├── Dockerfile                  # Application container
└── supervisord.conf            # Process management
```

## Documentation

For detailed documentation, visit: https://vkylamba.github.io/docs-iot-management/

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

See [LICENSE](LICENSE) file for details.
