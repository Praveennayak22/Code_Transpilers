#!/bin/bash
# Automated test completion detection and analysis trigger

OUTPUT_DIR="/projects/data/datasets/code_data/codeLLM_data/iitgn_pt_transpiler/test_output_v3/chunks/"
TEST_LOG="~/test_5k.log"
EXPECTED_FILES=5000

echo "Waiting for test completion..."
echo "Expected output files: $EXPECTED_FILES"
echo ""

# Poll for completion every 30 seconds
POLL_INTERVAL=30
MAX_WAITS=$((7200 / POLL_INTERVAL))  # Wait up to 2 hours
WAIT_COUNT=0

while [ $WAIT_COUNT -lt $MAX_WAITS ]; do
    FILE_COUNT=$(ls "$OUTPUT_DIR" 2>/dev/null | wc -l)
    PERCENT=$((100 * FILE_COUNT / EXPECTED_FILES))
    
    # Check if test process still running
    if ps aux | grep -q "[/]bin/bash.*test_5k_direct.sh"; then
        echo "[$(date '+%H:%M:%S')] Progress: $FILE_COUNT / $EXPECTED_FILES files ($PERCENT%)"
    else
        # Process finished
        echo ""
        echo "✓ Test process completed!"
        echo "Final file count: $FILE_COUNT / $EXPECTED_FILES"
        echo ""
        
        if [ $FILE_COUNT -ge $EXPECTED_FILES ]; then
            echo "✓ All 5,000 files processed!"
            echo ""
            echo "Running analysis..."
            echo "========================================"
            
            # Run analysis
            cd ~
            python3 compare_before_after.py
            
            echo "========================================"
            echo "Analysis complete!"
            exit 0
        else
            echo "⚠ Warning: Test completed but only $FILE_COUNT/$EXPECTED_FILES files found"
            echo "Proceeding with analysis anyway..."
            cd ~
            python3 compare_before_after.py
            exit 1
        fi
    fi
    
    # Check log file for completion message
    if tail -1 "$TEST_LOG" 2>/dev/null | grep -q "complete"; then
        echo ""
        echo "✓ Completion message detected in log"
        sleep 5  # Wait for final files to flush
        FILE_COUNT=$(ls "$OUTPUT_DIR" 2>/dev/null | wc -l)
        echo "Final file count: $FILE_COUNT / $EXPECTED_FILES"
        
        # Run analysis
        cd ~
        python3 compare_before_after.py
        exit 0
    fi
    
    sleep $POLL_INTERVAL
    WAIT_COUNT=$((WAIT_COUNT + 1))
done

echo ""
echo "⚠ Timeout: Test did not complete within 2 hours"
echo "Current status: $(ls $OUTPUT_DIR 2>/dev/null | wc -l) / $EXPECTED_FILES files"
exit 2
