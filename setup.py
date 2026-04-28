from setuptools import setup, find_packages
from pathlib import Path

long_description = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

setup(
    name="ugclaw",
    version="3.0.0",
    author="Abubakar Bello",
    author_email="abubakarbello3914@gmail.com",
    description="Autonomous AI agent with multi-provider LLM, browser automation, and Telegram control",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/abubakarbello3914/ugclaw",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "openai>=1.30.0",
        "anthropic>=0.25.0",
        "google-generativeai>=0.5.0",
        "requests>=2.31.0",
        "beautifulsoup4>=4.12.0",
        "playwright>=1.44.0",
    ],
    extras_require={
        "dev": ["pytest", "black", "ruff"],
    },
    entry_points={
        "console_scripts": [
            "ugclaw=ugclaw.main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "ugclaw": [],
        "": ["config/default_config.json"],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Security",
    ],
    keywords="ai agent llm automation pentesting telegram openai anthropic",
)
