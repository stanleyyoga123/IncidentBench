"""Render application comparisons of chaos-only workflow activity summaries."""
from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
import pandas as pd

from reporting.report_activity import ACTIVITY_LABELS


def activity_chart(summary: pd.DataFrame) -> Figure:
    """Compare numeric means and sample SD without inventing missing counts."""
    if summary.empty:
        figure, axis = plt.subplots(figsize=(12, 3))
        axis.text(.5, .5, 'No selected completed runs available',
                  ha='center', va='center', transform=axis.transAxes)
        axis.set_axis_off()
        return figure

    applications = sorted(summary.application.unique())
    groups = sorted(set(zip(summary.resource_type, summary.fault_type)))
    fault_labels = {
        'cpu': 'CPU', 'cpu-headroom': 'CPU headroom', 'memory': 'Memory',
        'delay': 'Delay', 'loss': 'Packet loss', 'bandwidth': 'Bandwidth',
        'capacity-loss': 'Capacity loss',
    }
    row_labels = [f'{resource.title()} · {fault_labels.get(fault, fault)}'
                  for resource, fault in groups]
    styles = {'online-boutique': ('#2878a8', 'o'),
              'sock-shop': ('#c35b43', 's'), 'teastore': ('#41966d', '^')}
    figure, axes = plt.subplots(1, 3, figsize=(15, max(5, len(groups) * .72 + 2.1)),
                                sharey=True)
    positions = {group: index for index, group in enumerate(groups)}
    slot_height = .72 / len(applications)
    for axis, (kind, title) in zip(axes, ACTIVITY_LABELS.items()):
        for row_index in range(len(groups)):
            if row_index % 2 == 0:
                axis.axhspan(row_index - .5, row_index + .5, color='#f4f5f6', zorder=0)
        for app_index, app in enumerate(applications):
            color, marker = styles[app]
            offset = (app_index - (len(applications) - 1) / 2) * slot_height
            rows = summary.loc[summary.application == app]
            for row in rows.itertuples(index=False):
                position = positions[(row.resource_type, row.fault_type)] + offset
                mean, std, count = (getattr(row, f'{kind}_{stat}')
                                    for stat in ('mean', 'std', 'n'))
                if pd.isna(mean):
                    axis.text(.98, position, 'Unknown (n=0)', color=color,
                              ha='right', va='center', fontsize=8,
                              transform=axis.get_yaxis_transform())
                    continue
                axis.errorbar(mean, position, xerr=std if pd.notna(std) else None,
                              fmt=marker, color=color, markersize=6, capsize=3,
                              markerfacecolor='white' if count == 1 else color,
                              elinewidth=1.3, zorder=3)
        axis.axvline(0, color='#8c959f', linewidth=.8, zorder=1)
        axis.set_title(title, fontsize=11, pad=12)
        axis.set_xlabel('Mean count per run', fontsize=10)
        axis.grid(axis='x', alpha=.18)
        axis.set_axisbelow(True)
        axis.spines[['top', 'right', 'left']].set_visible(False)
        axis.tick_params(axis='y', length=0)
        left, right = axis.get_xlim()
        axis.set_xlim(min(left, -.03 * max(right, 1)), max(right, 1))
        axis.set_ylim(len(groups) - .5, -.5)
    axes[0].set_yticks(range(len(groups)), row_labels, fontsize=10)
    legend = [Line2D([], [], color=styles[app][0],
                     marker=styles[app][1], linestyle='None',
                     label=app.replace('-', ' ').title(), markersize=7)
              for app in applications]
    figure.suptitle('Workflow activity by application and scenario type', fontsize=15, y=.98)
    figure.legend(handles=legend, loc='upper center', bbox_to_anchor=(.5, .945),
                  ncol=len(applications), frameon=False)
    figure.text(.02, .025,
                'Points: per-run means; whiskers: ± sample SD (variation, not standard error). '
                'Hollow points: n=1, SD unavailable.\n'
                'Unknown: n=0. No point: no completed runs in that group. '
                'Evaluable run counts: see table. Each panel uses its own count scale.',
                fontsize=9, color='#454b52', va='bottom')
    figure.tight_layout(rect=(0, .105, 1, .89), w_pad=2)
    return figure
