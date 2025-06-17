#!/usr/bin/env python3
"""
Test Runner for Jarvis Memory System

This script runs the comprehensive test suite for the memory system.
"""

import os
import sys
import pytest
import argparse
from pathlib import Path


def setup_test_environment():
    """Setup the test environment with required configurations"""
    # Add project root to Python path
    root_dir = Path(__file__).resolve().parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    # Set environment variables for testing
    os.environ["PYTHONPATH"] = str(root_dir)

    # Disable unnecessary warnings during tests
    if not os.environ.get("PYTHONWARNINGS"):
        os.environ["PYTHONWARNINGS"] = "ignore::DeprecationWarning"


def run_tests(test_type="all", verbose=False, failfast=False):
    """
    Run the specified tests

    Args:
        test_type (str): Type of tests to run ('unit', 'integration', or 'all')
        verbose (bool): Whether to show verbose output
        failfast (bool): Stop on first failure
    """
    setup_test_environment()

    # Base pytest arguments
    pytest_args = []

    # Add verbosity
    if verbose:
        pytest_args.extend(["-v", "-s"])

    # Add failfast
    if failfast:
        pytest_args.append("--exitfirst")

    # Select tests based on type
    if test_type == "unit":
        pytest_args.append("tests/test_amazon_mcp_server.py")
    elif test_type == "integration":
        pytest_args.append("tests/test_amazon_mcp_server_integration.py")
    else:  # all
        pytest_args.extend(
            [
                "tests/test_amazon_mcp_server.py",
                "tests/test_amazon_mcp_server_integration.py",
            ]
        )

    # Run tests and return exit code
    return pytest.main(pytest_args)


def main():
    """Main entry point for the test runner"""
    parser = argparse.ArgumentParser(description="Run Amazon MCP Server tests")
    parser.add_argument(
        "--type",
        choices=["unit", "integration", "all"],
        default="all",
        help="Type of tests to run",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show verbose output"
    )
    parser.add_argument("--failfast", action="store_true", help="Stop on first failure")

    args = parser.parse_args()

    # Print test configuration
    print(f"\nRunning {args.type} tests...")
    if args.verbose:
        print("Verbose output enabled")
    if args.failfast:
        print("Failfast enabled")
    print("\n" + "=" * 50 + "\n")

    # Run tests
    exit_code = run_tests(
        test_type=args.type, verbose=args.verbose, failfast=args.failfast
    )

    # Exit with appropriate code
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
