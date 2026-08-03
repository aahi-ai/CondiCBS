import re, sys
sys.path.insert(0, ".")
from src.condicbs.directives.library import SCENARIOS

def norm(v):
    if v is None:
        return None
    d = re.sub(r'\D', '', str(v))
    return d if d else str(v).strip().lower()

class_b = [s for s in SCENARIOS if s.directive_class == "B"]
correct = 0
for s in class_b:
    gt = s.oracle_ground_truth
    slacks = gt["branch_slacks"]
    guess = min(slacks, key=slacks.get)
    if norm(guess) == norm(gt["priority_agent"]):
        correct += 1

print(f"argmin(branch_slacks) baseline: {correct}/{len(class_b)} "
      f"({100*correct/len(class_b):.1f}%)")

# same thing at the root — should do badly, since these are divergent cases
root_correct = 0
for s in class_b:
    gt = s.oracle_ground_truth
    r = gt["root_slacks"]
    if norm(min(r, key=r.get)) == norm(gt["priority_agent"]):
        root_correct += 1
print(f"argmin(root_slacks) baseline:   {root_correct}/{len(class_b)} "
      f"({100*root_correct/len(class_b):.1f}%)")
