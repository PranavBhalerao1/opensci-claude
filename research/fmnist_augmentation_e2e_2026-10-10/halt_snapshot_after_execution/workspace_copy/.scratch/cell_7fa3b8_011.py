
import json
with open('context/plan.json') as f:
    plan = json.load(f)

# Look for fig2 description in deliverables or tasks
for phase in plan['phases']:
    for task in phase['tasks']:
        if 'fig2' in str(task) or 'gap_trajectory' in str(task).lower():
            print(f"Task {task['id']}: {task['title']}")
            print(f"  Outputs: {task.get('outputs', [])}")
            print(f"  Description snippet: {task.get('description','')[:200]}")
            print()
