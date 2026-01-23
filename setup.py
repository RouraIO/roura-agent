from setuptools import setup, find_packages

setup(
    name="roura-agent",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "typer>=0.12.0",
        "rich>=13.7.0",
        "httpx>=0.27.0",
        "pydantic>=2.7.0",
        "python-dotenv>=1.0.1",
    ],
    entry_points={
        "console_scripts": [
            "roura-agent=roura_agent.cli:app",
        ]
    },
)
