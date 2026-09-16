"""Offline agreement of independently supplied labels; never generates human labels."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
from .rubric import load_rubric


def agreement(labels, rubric):
    classes = {c.id: c.class_ids() for k in rubric.kinds.values() for c in k.criteria}
    groups = defaultdict(dict)
    for r in labels:
        criterion = r['criterion']
        if criterion not in classes or r['class'] not in classes[criterion]:
            raise ValueError('unknown rubric criterion/class')
        key = (r['item'], criterion)
        if r['reviewer'] in groups[key]:
            raise ValueError('duplicate reviewer label')
        groups[key][r['reviewer']] = r['class']
    reviewers = sorted({r['reviewer'] for r in labels})
    out = []
    for left_index, left in enumerate(reviewers):
        for right in reviewers[left_index+1:]:
            for criterion, allowed in classes.items():
                pairs = [(v[left], v[right]) for (item,c),v in groups.items() if c==criterion and left in v and right in v]
                size = len(allowed); matrix = [[0]*size for _ in range(size)]
                for a,b in pairs:
                    matrix[allowed.index(a)][allowed.index(b)] += 1
                n=len(pairs)
                if not n:
                    continue
                row=[sum(v) for v in matrix]; col=[sum(matrix[i][j] for i in range(size)) for j in range(size)]
                observed=sum(matrix[i][j]*(i-j)**2 for i in range(size) for j in range(size))/n
                expected=sum(row[i]*col[j]*(i-j)**2 for i in range(size) for j in range(size))/(n*n)
                out.append({'criterion':criterion,'reviewers':[left,right],'n':n,'classes':allowed,
                            'agreement':sum(matrix[i][i] for i in range(size))/n,
                            'quadratic_weighted_kappa':1-observed/expected if expected else None,
                            'confusion':matrix})
    return out


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels',type=Path,required=True,help='CSV columns: item,criterion,reviewer,class')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rubric',type=Path)
    args=parser.parse_args(argv)
    with args.labels.open(newline='') as f:
        labels=list(csv.DictReader(f))
    rubric=load_rubric(args.rubric)
    report={'rubric_hash':rubric.source_hash,'items':len({r['item'] for r in labels}),
            'minimum_calibration_items_met':len({r['item'] for r in labels})>=60,
            'agreements':agreement(labels,rubric)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':
    main()
