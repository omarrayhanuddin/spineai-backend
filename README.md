# spineai-backend

This is a FastAPI backend project utilizing the following technologies:

- **FastAPI**: A modern, fast (high-performance), web framework for building APIs.
- **Tortoise ORM**: An easy-to-use ORM for async applications.
- **Celery**: Distributed task queue for handling asynchronous tasks.
- **uv**: Python package manager used to manage dependencies.

## Getting Started

### Prerequisites
- Install [uv](https://github.com/astral-sh/uv) package manager.

### Installation
1. Clone the project:
   ```bash
   git clone https://github.com/omarrayhanuddin/spineai-backend.git
   ```
2. Navigate to the project directory and run:
   ```bash
   uv sync
   ```

### Running the Project
To start the application, use the following command:
```bash
uv run uvicorn app.main:app
```