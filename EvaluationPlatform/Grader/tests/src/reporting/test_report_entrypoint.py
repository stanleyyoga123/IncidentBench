"""Protect report destinations after consolidation into reporting."""
from reporting import report


def test_report_default_paths_use_root_output_folder():
    args = report.parser().parse_args([])
    assert args.output == report.GRADER_ROOT / 'output/report/report.md'
    assert args.grades_dir == report.GRADER_ROOT / 'output/grades'


def test_report_creates_destination_and_limits_application_sections(tmp_path):
    output = tmp_path / 'report/report.md'
    assert report.main(['--results-dir', str(tmp_path / 'results'),
                        '--grades-dir', str(tmp_path / 'grades'),
                        '--apps', 'teastore', '--output', str(output)]) == 0
    text = output.read_text()
    assert '## teastore' in text
    assert '## sock-shop' not in text
    assert '## online-boutique' not in text



def test_component_default_destinations_use_root_output_folder():
    from grader.cli import build_parser as grader_parser
    from grader.pipeline import GraderConfig
    from visualizer.cli import build_parser as visualizer_parser

    assert grader_parser().parse_args([]).output == report.GRADER_ROOT / 'output/grades'
    assert GraderConfig().output_path == report.GRADER_ROOT / 'output/grades'
    assert visualizer_parser().parse_args([]).output == report.GRADER_ROOT / 'output/visualizations'
