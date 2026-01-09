#!/bin/bash
# Comprehensive test runner for Azure Train Data Pipeline
# Usage: ./scripts/run-tests.sh [OPTIONS]
#
# Options:
#   --health       Run health checks only
#   --performance  Run performance tests only
#   --all          Run all tests (default)
#   --ci           Run in CI mode (exit on first failure)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Emoji support
CHECK="✅"
CROSS="❌"
WARNING="⚠️"
ROCKET="🚀"
GEAR="⚙️"
DATABASE="🗄️"

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PATH="$PROJECT_ROOT/venv"
TEST_RESULTS_DIR="$PROJECT_ROOT/test-results"

# Default options
RUN_CONNECTION=true
RUN_HEALTH=true
RUN_PERFORMANCE=true
CI_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --health)
            RUN_CONNECTION=false
            RUN_PERFORMANCE=false
            shift
            ;;
        --performance)
            RUN_CONNECTION=false
            RUN_HEALTH=false
            shift
            ;;
        --connection)
            RUN_HEALTH=false
            RUN_PERFORMANCE=false
            shift
            ;;
        --all)
            RUN_CONNECTION=true
            RUN_HEALTH=true
            RUN_PERFORMANCE=true
            shift
            ;;
        --ci)
            CI_MODE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --health       Run health checks only"
            echo "  --performance  Run performance tests only"
            echo "  --connection   Run connection test only"
            echo "  --all          Run all tests (default)"
            echo "  --ci           Run in CI mode (exit on first failure)"
            echo "  --help         Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Functions
print_header() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_section() {
    echo ""
    echo -e "${YELLOW}──────────────────────────────────────────────────────────────${NC}"
    echo -e "${YELLOW}  $1${NC}"
    echo -e "${YELLOW}──────────────────────────────────────────────────────────────${NC}"
}

print_success() {
    echo -e "${GREEN}${CHECK} $1${NC}"
}

print_error() {
    echo -e "${RED}${CROSS} $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}${WARNING} $1${NC}"
}

print_info() {
    echo -e "${BLUE}${GEAR} $1${NC}"
}

# Start
print_header "${DATABASE} Azure Train Data Pipeline - Test Suite ${DATABASE}"

echo "Project Root: $PROJECT_ROOT"
echo "Test Results: $TEST_RESULTS_DIR"
echo "CI Mode: $CI_MODE"
echo ""

# Create test results directory
mkdir -p "$TEST_RESULTS_DIR"

# Track overall status
OVERALL_STATUS=0

# Step 1: Check environment
print_section "Environment Setup"

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    print_error "Virtual environment not found at $VENV_PATH"
    echo "Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi
print_success "Virtual environment found"

# Activate virtual environment
print_info "Activating virtual environment..."
source "$VENV_PATH/bin/activate"
print_success "Virtual environment activated"

# Check Python version
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
print_info "Python version: $PYTHON_VERSION"

# Check if required packages are installed
print_info "Checking required packages..."
REQUIRED_PACKAGES=("pyodbc" "requests" "azure-functions")
for package in "${REQUIRED_PACKAGES[@]}"; do
    if python -c "import $package" 2>/dev/null; then
        print_success "$package is installed"
    else
        print_error "$package is not installed"
        echo "Run: pip install -r requirements.txt"
        exit 1
    fi
done

# Check for connection string
print_info "Checking database connection configuration..."
if [ -f "$PROJECT_ROOT/local.settings.json" ]; then
    if grep -q "SQL_CONNECTION_STRING" "$PROJECT_ROOT/local.settings.json"; then
        print_success "Connection string found in local.settings.json"
    else
        print_warning "SQL_CONNECTION_STRING not found in local.settings.json"
    fi
elif [ -n "$SQL_CONNECTION_STRING" ]; then
    print_success "Connection string found in environment variable"
else
    print_error "No connection string found"
    echo "Set SQL_CONNECTION_STRING environment variable or add to local.settings.json"
    exit 1
fi

# Step 2: Run Connection Test
if [ "$RUN_CONNECTION" = true ]; then
    print_section "Database Connection Test"

    TEST_OUTPUT="$TEST_RESULTS_DIR/connection-test.log"

    if python "$PROJECT_ROOT/tests/test_database.py" > "$TEST_OUTPUT" 2>&1; then
        print_success "Connection test passed"
        cat "$TEST_OUTPUT"
    else
        print_error "Connection test failed"
        cat "$TEST_OUTPUT"
        OVERALL_STATUS=1
        if [ "$CI_MODE" = true ]; then
            exit 1
        fi
    fi
fi

# Step 3: Run Health Check
if [ "$RUN_HEALTH" = true ]; then
    print_section "Database Health Check"

    TEST_OUTPUT="$TEST_RESULTS_DIR/health-check.log"
    JSON_OUTPUT="$TEST_RESULTS_DIR/health-check.json"

    if python "$PROJECT_ROOT/tests/test_database.py" --health > "$TEST_OUTPUT" 2>&1; then
        print_success "Health check passed"
        cat "$TEST_OUTPUT"

        # Try to extract JSON for reporting
        if command -v jq &> /dev/null; then
            print_info "Generating JSON report..."
            # Note: This would require modifying test_database.py to output JSON
            # For now, we'll just show the text output
        fi
    else
        EXIT_CODE=$?
        if [ $EXIT_CODE -eq 1 ]; then
            print_warning "Health check completed with warnings (degraded status)"
            cat "$TEST_OUTPUT"
        else
            print_error "Health check failed"
            cat "$TEST_OUTPUT"
            OVERALL_STATUS=1
            if [ "$CI_MODE" = true ]; then
                exit 1
            fi
        fi
    fi
fi

# Step 4: Run Performance Test
if [ "$RUN_PERFORMANCE" = true ]; then
    print_section "Database Performance Benchmark"

    TEST_OUTPUT="$TEST_RESULTS_DIR/performance-test.log"

    if python "$PROJECT_ROOT/tests/test_database.py" --performance > "$TEST_OUTPUT" 2>&1; then
        print_success "Performance test completed"
        cat "$TEST_OUTPUT"

        # Parse and highlight slow operations
        echo ""
        print_info "Analyzing performance results..."
        if grep -q "Poor" "$TEST_OUTPUT"; then
            print_warning "Some operations are performing poorly (>500ms)"
            grep "Poor" "$TEST_OUTPUT" | sed 's/^/  /'
        elif grep -q "Fair" "$TEST_OUTPUT"; then
            print_warning "Some operations could be optimized (200-500ms)"
            grep "Fair" "$TEST_OUTPUT" | sed 's/^/  /'
        else
            print_success "All operations performing well!"
        fi
    else
        print_error "Performance test failed"
        cat "$TEST_OUTPUT"
        OVERALL_STATUS=1
        if [ "$CI_MODE" = true ]; then
            exit 1
        fi
    fi
fi

# Step 5: Summary
print_section "Test Summary"

echo "Test results saved to: $TEST_RESULTS_DIR"
echo ""

if [ "$RUN_CONNECTION" = true ]; then
    echo "  - Connection test: $TEST_RESULTS_DIR/connection-test.log"
fi

if [ "$RUN_HEALTH" = true ]; then
    echo "  - Health check: $TEST_RESULTS_DIR/health-check.log"
fi

if [ "$RUN_PERFORMANCE" = true ]; then
    echo "  - Performance test: $TEST_RESULTS_DIR/performance-test.log"
fi

echo ""

# Final status
if [ $OVERALL_STATUS -eq 0 ]; then
    print_header "${ROCKET} All Tests Passed! ${ROCKET}"
    echo ""
    echo "Next steps:"
    echo "  1. Review test results in $TEST_RESULTS_DIR"
    echo "  2. Check monitoring dashboard in Azure Portal"
    echo "  3. Deploy alert rules: ./scripts/deploy-monitoring.sh"
    echo ""
else
    print_header "${CROSS} Some Tests Failed ${CROSS}"
    echo ""
    echo "Please review the test output above for details."
    echo "Check logs in $TEST_RESULTS_DIR for more information."
    echo ""
    echo "Troubleshooting:"
    echo "  1. Verify database connection string"
    echo "  2. Check firewall rules in Azure SQL"
    echo "  3. Review error messages in test logs"
    echo "  4. See MONITORING.md for common issues"
    echo ""
fi

# Deactivate virtual environment
deactivate

exit $OVERALL_STATUS
