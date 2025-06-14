#!/usr/bin/env python3
"""
Test Runner for Jarvis Memory System

This script runs the comprehensive test suite for the memory system.
"""

import sys
import subprocess
from pathlib import Path

def install_test_dependencies():
    """Install required test dependencies"""
    dependencies = ["pytest", "pytest-asyncio", "requests"]
    
    print("📦 Installing test dependencies...")
    for dep in dependencies:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
            print(f"✅ Installed {dep}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install {dep}: {e}")
            return False
    return True

def run_tests():
    """Run the memory system tests"""
    print("🧪 Running Memory System Tests")
    print("=" * 50)
    
    # Ensure we're in the project directory
    project_root = Path(__file__).parent
    test_file = project_root / "tests" / "test_memory_system.py"
    
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        return 1
    
    # Run the tests
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            str(test_file),
            "-v",
            "--tb=short"
        ], cwd=project_root)
        
        return result.returncode
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return 1

def main():
    """Main test runner function"""
    print("🚀 Jarvis Memory System Test Runner")
    print("=" * 40)
    
    # Install dependencies
    if not install_test_dependencies():
        print("❌ Failed to install test dependencies")
        return 1
    
    # Run tests
    exit_code = run_tests()
    
    if exit_code == 0:
        print("\n🎉 All tests passed!")
        print("✅ Memory system is functioning correctly")
    else:
        print(f"\n❌ Tests failed (exit code: {exit_code})")
        print("Please check the output above for details")
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main()) 