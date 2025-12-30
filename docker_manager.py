import subprocess
import time
import os
import uuid

class DockerWorker:
    def __init__(self, image="oeis-runner", timeout=5, use_host_nix_store=False):
        self.image = "alpine:latest" if use_host_nix_store else image
        self.container_name = f"oeis-worker-{uuid.uuid4().hex[:8]}"
        self.timeout = timeout
        self.use_host_nix_store = use_host_nix_store
        self.is_running = False

        # Paths - assuming this runs from oeisprog/
        # Adjust these if your directory structure changes
        self.abs_prog_dir = os.path.abspath("progs")
        self.abs_sanitized_dir = os.path.abspath("sanitized")
        self.abs_runner = os.path.abspath("sandbox_runner.py")
        
        # Determine which directory to mount based on existence
        self.mount_dir = self.abs_prog_dir if os.path.exists(self.abs_prog_dir) else self.abs_sanitized_dir
        self.mount_target = "/opt/oeis/progs"

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        # Ensure image exists (optional check, or let run fail)
        print(f"[Docker] Starting worker container {self.container_name}...")
        
        cmd = [
            "docker", "run", "-d", "--rm",
            "--name", self.container_name,
            "--network", "none",
            # Mount runner script
            "-v", f"{self.abs_runner}:/opt/oeis/sandbox_runner.py:ro",
            # Mount the programs directory
            "-v", f"{self.mount_dir}:{self.mount_target}:ro",
        ]

        if self.use_host_nix_store:
            # NixOS Host Integration
            cmd.extend([
                "-v", "/nix/store:/nix/store:ro",
                "-v", "/run/current-system/sw/bin:/host-bin:ro",
                # Pass essential env vars if needed, but PATH is set below
                "-e", "PATH=/host-bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            ])
            # We might need to mount specific license locations for proprietary tools
            # e.g. -v /etc/mathematica:/etc/mathematica:ro
        
        cmd.extend([
            # Keep alive
            self.image,
            "sleep", "infinity"
        ])
        
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
            self.is_running = True
            time.sleep(0.5) # Allow container to stabilize
        except subprocess.CalledProcessError as e:
            print(f"[Docker] Failed to start container: {e}")
            raise

    def stop(self):
        if self.is_running:
            print(f"[Docker] Stopping worker {self.container_name}...")
            subprocess.run(["docker", "kill", self.container_name], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.is_running = False

    def run_script(self, a_num, file_path, lang, offset=0, count=10):
        if not self.is_running:
            raise RuntimeError("Container is not running")

        # Determine path relative to the mounted directory
        # We need to support both 'progs' and 'sanitized' or whatever was mounted
        try:
            rel_path = os.path.relpath(file_path, self.mount_dir)
        except ValueError:
            # Fallback if file is not in the mounted dir
            return "", "File path not in mounted directory", -1

        container_path = f"{self.mount_target}/{rel_path}"

        # Determine interpreter
        if self.use_host_nix_store:
            # Use host python to run the runner
            interpreter = ["/host-bin/python3"]
        else:
            # Use image sage-python
            interpreter = ["sage", "-python"]

        # Command to run INSIDE the container
        exec_cmd = [
            "docker", "exec",
            self.container_name
        ] + interpreter + [
            "/opt/oeis/sandbox_runner.py",
            "--file", container_path,
            "--lang", lang,
            "--id", a_num,
            "--offset", str(offset),
            "--count", str(count),
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
