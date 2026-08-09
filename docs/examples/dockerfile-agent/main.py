import json
import sys

task = json.load(sys.stdin)
result = {"status": "success", "output": f"received: {task['input']}"}
print(json.dumps({"result": result, "trace": {"spans": []}}))
