from setuptools import setup, find_packages

setup(
    name="render-hybrid-cache",
    version="1.0.0",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[],
    extras_require={
        "redis": ["redis>=4.0.0"],
        "test": ["pytest>=7.0.0", "pytest-asyncio>=0.20.0"],
    },
)
