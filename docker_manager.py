import subprocess
import time
import os
import uuid
import sys
import config

class DockerWorker:
    def __init__(self, timeout=5, use_host_nix_store=False):
        self.image = "debian:bookworm-slim" if use_host_nix_store else "python:3.9-slim"
        self.container_name = f"oeis-worker-{uuid.uuid4().hex[:8]}"
        self.timeout = timeout
        self.use_host_nix_store = use_host_nix_store
        self.is_running = False

        # Paths
        self.cwd = os.getcwd() # Should be .../oeisprog
        self.oeisprog_dir = self.cwd
        self.oeisdata_dir = config.get_oeis_data_dir()
        
        # Container Paths (Mirror Host Paths for venv compatibility)
        self.cont_prog_dir = self.oeisprog_dir
        self.cont_data_dir = self.oeisdata_dir

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        print(f"[Docker] Starting worker container {self.container_name}...")
        
        cmd = [
            "docker", "run", "-d", "--rm",
            "--name", self.container_name,
            "--network", "none",
            "--workdir", self.cont_prog_dir,
            # Mount oeisprog (code + scripts)
            "-v", f"{self.oeisprog_dir}:{self.cont_prog_dir}:ro",
            # Mount oeisdata (data)
            "-v", f"{self.oeisdata_dir}:{self.cont_data_dir}:ro",
        ]

        if self.use_host_nix_store:
            # NixOS Host Integration
            cmd.extend([
                "-v", "/nix/store:/nix/store:ro",
                "-v", "/run/current-system/sw/bin:/host-bin:ro",
                # Pass PATH so it finds python3, sage, etc.
                "-e", "PATH=/host-bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            ])
        
        cmd.extend([
            self.image,
            "sleep", "infinity"
        ])
        
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
            self.is_running = True
            time.sleep(0.5) 
        except subprocess.CalledProcessError as e:
            print(f"[Docker] Failed to start container: {e}")
            raise

    def stop(self):
        if self.is_running:
            print(f"[Docker] Stopping worker {self.container_name}...")
            subprocess.run(["docker", "kill", self.container_name], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.is_running = False

    def run_test_sequence_py(self, a_num):
        """
        Runs test_sequence.py inside the container for the given A-number.
        """
        if not self.is_running:
            raise RuntimeError("Container is not running")

        # Determine Interpreter
        venv_python = os.path.join(self.cont_prog_dir, ".venv", "bin", "python")
        
        if self.use_host_nix_store and os.path.exists(os.path.join(self.oeisprog_dir, ".venv", "bin", "python")):
            # If using host store and venv exists on host (mirrored to container), use it
            interpreter = venv_python
        elif self.use_host_nix_store:
             interpreter = "/host-bin/python3"
        else:
             interpreter = "python3"

        # We run test_sequence.py directly
        exec_cmd = [
            "docker", "exec",
            self.container_name,
            interpreter, "test_sequence.py", 
            a_num,
            "--timeout", str(self.timeout)
        ]

        try:
            result = subprocess.run(
                exec_cmd, 
                capture_output=True, 
                text=True, 
                timeout=self.timeout + 2
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "Docker Exec Timeout", -1
        except Exception as e:
            return "", str(e), -1