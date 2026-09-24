"""Run a synthetic offline example: python main.py."""

from dataclasses import asdict
import json

from recruiterradar.models import CandidateProfile, Opportunity
from recruiterradar.pipeline import Pipeline
from recruiterradar.providers.demo import DemoMatcher, DemoSearch


def main():
    pipeline = Pipeline(DemoSearch(), DemoMatcher(), simulated=True)
    result = pipeline.run(
        CandidateProfile(skills=("Python", "SQL")),
        Opportunity("Seeking a Python and SQL engineer.", company="Example Robotics"),
    )
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
