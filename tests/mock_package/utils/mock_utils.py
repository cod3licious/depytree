class DataLoader:
    def __init__(self, source):
        self.source = source
        self.data = None

    def load(self):
        parser = DataParser()
        self.data = parser.parse(self.source)

    def get_data(self):
        return self.data


class DataParser:
    def parse(self, source):
        # Pretend to parse something
        cleaner = DataCleaner()
        return cleaner.clean(source)


class DataCleaner:
    def clean(self, raw_data):
        # Fake cleaning logic
        return raw_data


class ReportGenerator:
    def __init__(self, data):
        self.data = data

    def generate(self):
        # Fake report generation
        formatter = ReportFormatter()
        return formatter.format(self.data)


class ReportFormatter:
    def format(self, data):
        return f"Formatted report for: {data}"


def run_pipeline(source):
    loader = DataLoader(source)
    loader.load()
    data = loader.get_data()

    report = ReportGenerator(data)
    return report.generate()


def test_pipeline():
    dummy_source = "mock_source_data"
    return run_pipeline(dummy_source)
