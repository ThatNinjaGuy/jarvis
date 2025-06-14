# Jarvis Memory System Test Suite

This directory contains comprehensive tests for the Jarvis multi-tiered memory system functionality.

## Overview

The test suite validates:

- **Memory System Availability**: Ensures all memory services are properly initialized
- **User Profile Management**: Tests user profile creation, retrieval, and preference management
- **Memory Storage & Retrieval**: Validates memory storage, search, and contextual retrieval
- **Session Management**: Tests enhanced session creation and memory integration
- **API Endpoints**: Validates REST API functionality for memory operations
- **Graceful Fallback**: Ensures system works when memory components are unavailable

## Test Structure

### Core Memory Tests (`TestMemorySystem`)

- `test_memory_system_availability()` - Verifies memory services are active
- `test_user_profile_creation()` - Tests user profile creation and default preferences
- `test_user_preferences_management()` - Tests preference updates and retrieval
- `test_memory_storage_and_retrieval()` - Tests memory storage and semantic search
- `test_contextual_memory_retrieval()` - Tests context-aware memory retrieval
- `test_enhanced_session_management()` - Tests session creation with memory context
- `test_agent_session_integration()` - Tests agent session memory integration
- `test_memory_system_graceful_fallback()` - Tests fallback behavior

### API Tests (`TestMemorySystemAPI`)

- `test_health_endpoint()` - Tests system health endpoint
- `test_memory_status_endpoint()` - Tests memory system status endpoint
- `test_user_profile_api()` - Tests user profile API endpoints
- `test_memory_storage_api()` - Tests memory storage and search APIs

## Running Tests

### Option 1: Using the Test Runner (Recommended)

```bash
python run_tests.py
```

This will:

- Install required test dependencies (pytest, pytest-asyncio, requests)
- Run the complete test suite
- Provide detailed output and summary

### Option 2: Using pytest directly

```bash
# Install dependencies first
pip install pytest pytest-asyncio requests

# Run all tests
pytest tests/test_memory_system.py -v

# Run specific test class
pytest tests/test_memory_system.py::TestMemorySystem -v

# Run specific test
pytest tests/test_memory_system.py::TestMemorySystem::test_memory_storage_and_retrieval -v
```

### Option 3: Run from within the test file

```bash
python tests/test_memory_system.py
```

## Prerequisites

1. **Memory System Setup**: Ensure the memory system is properly configured:
   - Database tables created
   - ChromaDB vector database initialized
   - Vertex AI embeddings configured

2. **API Server Running** (for API tests): Start the Jarvis API server:

   ```bash
   python app/main.py
   ```

3. **Environment Variables**: Ensure required environment variables are set:
   - `GOOGLE_CLOUD_PROJECT`
   - `GOOGLE_APPLICATION_CREDENTIALS` (if not using default credentials)

## Test Configuration

The test suite uses `pytest.ini` for configuration:

- Verbose output enabled
- Async test support
- Warning suppression for cleaner output
- Custom markers for test categorization

## Expected Output

Successful test run should show:

```
🎉 All tests passed!
✅ Memory system is functioning correctly
```

## Troubleshooting

### Common Issues

1. **Memory System Not Available**
   - Tests will skip gracefully if memory system is not initialized
   - Check database and vector database connections

2. **API Server Not Running**
   - API tests will skip if server is not accessible on localhost:8001
   - Start the server with `python app/main.py`

3. **Vertex AI Authentication**
   - Ensure Google Cloud credentials are properly configured
   - Check that Vertex AI API is enabled in your project

4. **Database Connection Issues**
   - Verify database URL and credentials
   - Ensure database tables are created

### Test Failures

If tests fail:

1. Check the detailed error output
2. Verify all prerequisites are met
3. Check system logs for additional context
4. Ensure no conflicting processes are running

## Test Data

The test suite:

- Creates temporary test users with unique IDs
- Stores test memories and preferences
- Cleans up after test completion
- Uses isolated test data to avoid conflicts

## Continuous Integration

This test suite is designed to be CI/CD friendly:

- Automatic dependency installation
- Graceful handling of missing services
- Clear exit codes for automation
- Comprehensive coverage reporting

## Contributing

When adding new tests:

1. Follow the existing naming conventions
2. Add appropriate async/await for async operations
3. Include proper error handling and cleanup
4. Add descriptive docstrings
5. Test both success and failure scenarios
