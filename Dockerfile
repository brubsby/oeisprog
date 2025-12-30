# Use the official SageMath image which contains Python, PARI/GP, GAP, Maxima, etc.
FROM sagemath/sagemath:latest

# Set the working directory
WORKDIR /opt/oeis

# By default, we run as the 'sage' user provided by the image
USER sage

# The entrypoint runs our sandbox runner using Sage's python environment
# We assume sandbox_runner.py will be mounted at /opt/oeis/sandbox_runner.py
ENTRYPOINT ["sage", "-python", "/opt/oeis/sandbox_runner.py"]
