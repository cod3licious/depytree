import mock_package.utils.mock_utils as utils
from mock_package.utils.mock_utils import (
    DataCleaner,
    DataLoader,
    DataParser,
    ReportGenerator,
)


def preprocess_source(source):
    cleaner = DataCleaner()
    return cleaner.clean(source)


def parse_and_validate(source):
    parser = DataParser()
    parsed = parser.parse(source)
    is_valid = True
    return parsed if is_valid else None


def generate_summary_report(source):
    data = preprocess_source(source)
    report = ReportGenerator(data)
    return report.generate()


def run_full_process(source):
    result = utils.run_pipeline(source)
    summary = generate_summary_report(source)
    return {
        "full_result": result,
        "summary": summary,
    }


def inspect_loader(source):
    loader = DataLoader(source)
    loader.load()
    return loader.get_data()


def run_pipeline():
    return None


def main():
    source = "example_input"
    results = run_full_process(source)
    print("Results:", results)
