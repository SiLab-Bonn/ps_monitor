python3 Asnapshot.py -c "CLEAR_ON SW_REFIN CLEAR_OFF SW_SUB" -ip 10.32.208.153 -p 5556 && python3 Bsnapshot.py -c "GATE_ON1 GATE_OFF" -ip 10.32.208.144 -p 5556 && python3 results_into_clipboard.py
