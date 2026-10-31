"""Conservative, source-linked classification for archived FRED H.10 null observations.

Curated Fed Board material (not model-derived fill values). Missing records remain NaN;
classification is research-only and never authorizes historical-vintage training.
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path

# Each entry is separately auditable and scoped to one date. An 'ND' on the
# H.10 country/index table supports that release's unavailability only; it does
# not mean markets were closed or that an alternative price can be fabricated.
H10_EVIDENCE = {
    '2017-01-20': ('ARCHIVED_H10_ND','https://www.federalreserve.gov/releases/h10/20170123/default.htm',
                   'Archived H.10 table marks South Korea won and broad dollar index ND.'),
    '2018-03-02': ('FED_BOARD_CLOSED_WEATHER','https://www.federalreserve.gov/newsevents/2018-march.htm',
                   'Fed Board calendar reports closure due to severe weather; direct series ND not independently matched.'),
    '2018-03-21': ('FED_BOARD_CLOSED_WEATHER','https://www.federalreserve.gov/newsevents/2018-march.htm',
                   'Fed Board calendar reports closure; statistical releases postponed, except specified exceptions.'),
    '2018-12-24': ('ARCHIVED_H10_ND','https://www.federalreserve.gov/releases/h10/20181231/',
                   'Archived H.10 has ND for South Korea won and dollar index on Dec 24.'),
    '2019-01-14': ('ARCHIVED_H10_ND','https://www.federalreserve.gov/releases/h10/20190122/',
                   'Archived H.10 records ND on Jan 14; Board calendar also reports weather closure.'),
    '2019-02-20': ('FED_BOARD_CLOSED_WEATHER','https://www.federalreserve.gov/newsevents/2019-february.htm',
                   'Fed Board calendar reports weather closure and delayed statistical releases.'),
    '2019-12-24': ('PUBLISHED_H10_BROAD_INDEX_CONFLICT','https://www.federalreserve.gov/releases/h10/20191230/',
                   'Archived H.10 BROAD JAN06=100 value is present on Dec 24 while current DTWEXBGS is NaN; verify historical series revision, do not fill.'),
    '2020-11-27': ('ARCHIVED_H10_ND','https://www.federalreserve.gov/releases/h10/20201130/',
                   'Archived H.10 has ND for South Korea won and dollar index on Friday after Thanksgiving.'),
    '2020-12-24': ('ARCHIVED_H10_ND','https://www.federalreserve.gov/releases/h10/20201228/',
                   'Archived H.10 has ND for South Korea won and dollar index on Dec 24.'),
    '2021-01-20': ('ARCHIVED_H10_ND','https://www.federalreserve.gov/releases/h10/20210125/',
                   'Archived H.10 has ND for South Korea won and dollar index on Inauguration Day.'),
}


def classify_fred_h10(date: str, indicator: str) -> dict:
    if indicator not in ('DEXKOUS', 'DTWEXBGS'):
        raise ValueError('UNSUPPORTED_SERIES')
    if date not in H10_EVIDENCE:
        return {'evidence_class':'UNCLASSIFIED','evidence_url':'',
                'evidence_note':'Official H.10 evidence not yet reviewed',
                'historical_imputation_allowed':False, 'pit_training_eligible':False}
    kind, url, note = H10_EVIDENCE[date]
    # Only the broad index conflicts on Dec 24, 2019. If new series anomaly
    # emerges, do not extrapolate evidence to a different instrument.
    if date == '2019-12-24' and indicator != 'DTWEXBGS':
        return {'evidence_class':'UNCLASSIFIED','evidence_url':'',
                'evidence_note':'Historical conflict pertains only to DTWEXBGS',
                'historical_imputation_allowed':False, 'pit_training_eligible':False}
    return {'evidence_class':kind,'evidence_url':url,'evidence_note':note,
            'historical_imputation_allowed':False,'pit_training_eligible':False}


def reconcile_fred_fx_nulls(rows: list[dict]) -> tuple[list[dict],dict]:
    detailed=[]
    for row in rows:
        date=str(row['date']); indicator=str(row['indicator'])
        detailed.append({**row, **classify_fred_h10(date,indicator)})
    by_class=dict(Counter(r['evidence_class'] for r in detailed))
    return detailed, {
        'schema':'kalman-fred-h10-evidence-v1',
        'rows_total':len(detailed),
        'unique_dates':len({r['date'] for r in detailed}),
        'classification_counts':by_class,
        'official_nd_or_board_closure_rows':sum(by_class.get(x,0) for x in ('ARCHIVED_H10_ND','FED_BOARD_CLOSED_WEATHER')),
        'official_archive_conflict_rows':by_class.get('PUBLISHED_H10_BROAD_INDEX_CONFLICT',0),
        'unclassified_rows':by_class.get('UNCLASSIFIED',0),
        'historical_fred_values_modified':False,
        'point_in_time_training_eligible':False,
        'notes':'Archived H.10/Board closure evidence is provenance only: retain NaN; latest-revised data are not vintage PIT.'
    }