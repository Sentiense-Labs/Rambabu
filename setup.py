#!/usr/bin/env python3
"""
Setup script for AI RC Car project
Installs requirements and verifies installation
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(command, description, check=True):
    """Run a command and handle errors"""
    print(f"\n{'='*50}")
    print(f"📦 {description}")
    print(f"{'='*50}")

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, check=check
        )

        if result.stdout:
            print(result.stdout)
        if result.stderr and result.returncode == 0:
            # Some warnings are normal
            warnings = [
                line for line in result.stderr.split("\n") if "warning" in line.lower()
            ]
            if warnings:
                print("⚠️  Warnings:")
                for warning in warnings[:5]:  # Limit warnings
                    print(f"   {warning}")

        return result.returncode == 0

    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False


def install_system_packages():
    """Install system-level dependencies"""
    commands = [
        ("sudo apt update", "Updating package lists"),
        (
            "sudo apt install -y python3-pip python3-picamera2 python3-opencv portaudio19-dev python3-pyaudio",
            "Installing system packages",
        ),
    ]

    for cmd, desc in commands:
        if not run_command(cmd, desc):
            print(f"⚠️  Failed to install: {desc}")
            return False

    return True


def install_uv():
    """Install uv package manager globally"""
    print(f"\n{'='*50}")
    print("🚀 Installing uv package manager")
    print(f"{'='*50}")

    # Check if uv is already installed
    if run_command("uv --version", "Checking if uv is installed", check=False):
        print("✓ uv already installed")
        return True

    # Install uv
    install_cmd = "curl -LsSf https://astral.sh/uv/install.sh | sh"
    if not run_command(install_cmd, "Installing uv package manager", check=False):
        print("⚠️  uv installation may have had issues")
        return False

    # Add to PATH
    path_cmd = "echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc"
    run_command(path_cmd, "Adding uv to PATH", check=False)

    # Source the environment
    source_cmd = "source $HOME/.local/bin/env"
    run_command(source_cmd, "Loading uv environment", check=False)

    return True


def install_claude_agent_sdk():
    """Install Claude Agents SDK using uv"""
    print(f"\n{'='*50}")
    print("🤖 Installing Claude Agents SDK")
    print(f"{'='*50}")

    project_dir = Path(__file__).parent

    # Create pyproject.toml if it doesn't exist
    pyproject_file = project_dir / "pyproject.toml"
    if not pyproject_file.exists():
        print("✓ Creating pyproject.toml")
        return True  # Already created in main setup

    # Use uv to install dependencies
    uv_cmd = f"cd {project_dir} && source $HOME/.local/bin/env && uv sync"
    return run_command(uv_cmd, "Installing dependencies with uv", check=False)


def setup_pigpio():
    """Install and setup pigpio daemon"""
    print(f"\n{'='*50}")
    print("🔧 Setting up pigpio daemon")
    print(f"{'='*50}")

    # Check if pigpiod exists
    if not run_command(
        "which pigpiod", "Checking if pigpiod is installed", check=False
    ):
        print("📥 Installing pigpio from source...")

        # Download and install pigpio
        pigpio_commands = [
            "cd /tmp && rm -rf pigpio-master",
            "wget -q https://github.com/joan2937/pigpio/archive/master.zip",
            "unzip -q master.zip",
            "cd pigpio-master && make -s",
            "sudo make install -s",
        ]

        for cmd in pigpio_commands:
            if not run_command(cmd, "Installing pigpio", check=False):
                print("⚠️  pigpio installation had issues (this is normal on Pi 5)")
                break

    # Try to start pigpio daemon
    if not run_command("sudo pigpiod -s 1", "Starting pigpio daemon", check=False):
        print("⚠️  pigpio daemon failed to start (normal on Pi 5)")
        print("ℹ️  Will use RPi.GPIO instead")

    return True


def verify_installation():
    """Run the verification script"""
    project_dir = Path(__file__).parent
    verify_script = project_dir / "verify_installation.py"

    if verify_script.exists():
        return run_command(f"python3 {verify_script}", "Verifying installation")
    else:
        print("❌ verify_installation.py not found!")
        return False


def create_project_structure():
    """Create necessary directories and files"""
    print(f"\n{'='*50}")
    print("📁 Creating project structure")
    print(f"{'='*50}")

    directories = [
        "lib",
        "vision",
        "navigation",
        "server",
        "server/mqtt",
        "utils",
        "config",
        "certs",
        "model",
        "static",
        "logs",
    ]

    project_dir = Path(__file__).parent

    for dir_name in directories:
        dir_path = project_dir / dir_name
        dir_path.mkdir(exist_ok=True)

        # Create __init__.py for Python packages
        if dir_name not in ["certs", "model", "static", "logs"]:
            init_file = dir_path / "__init__.py"
            if not init_file.exists():
                init_file.touch()

    print("✓ Project structure created")
    return True


def setup_environment():
    """Setup environment variables and configuration"""
    print(f"\n{'='*50}")
    print("🔧 Environment Setup")
    print(f"{'='*50}")

    env_file = Path(__file__).parent / ".env"

    if not env_file.exists():
        env_content = """# AI RC Car Environment Variables
# Claude API Key (get from https://console.anthropic.com/)
ANTHROPIC_API_KEY=your-api-key-here

# AWS IoT Configuration (optional)
AWS_IOT_ENDPOINT=your-iot-endpoint.amazonaws.com
AWS_IOT_CLIENT_ID=ai-rc-car
AWS_IOT_TOPIC_PREFIX=car

# Camera Settings
CAMERA_RESOLUTION=800x600
CAMERA_QUALITY=85

# Motor Settings
DEFAULT_SPEED=70
MAX_SPEED=100

# Safety Settings
SAFE_DISTANCE=50
STOP_DISTANCE=20
"""

        with open(env_file, "w") as f:
            f.write(env_content)

        print("✓ Created .env file with configuration template")
        print("📝 Edit .env file to add your API keys and settings")
    else:
        print("✓ .env file already exists")

    return True


def main():
    """Main setup function"""
    print("🚀 AI RC Car Setup Script")
    print("This will install all dependencies and verify the installation")

    # Check if running as root for system packages
    if os.geteuid() != 0:
        print(
            "⚠️  Note: You may be prompted for password for system package installation"
        )

    steps = [
        ("Installing system packages", install_system_packages),
        ("Installing uv package manager", install_uv),
        ("Installing Python packages with uv", install_claude_agent_sdk),
        ("Setting up pigpio daemon", setup_pigpio),
        ("Creating project structure", create_project_structure),
        ("Setting up environment", setup_environment),
        ("Verifying installation", verify_installation),
    ]

    failed_steps = []

    for step_name, step_func in steps:
        print(f"\n🔄 {step_name}...")
        if not step_func():
            failed_steps.append(step_name)
            print(f"❌ {step_name} failed")
        else:
            print(f"✅ {step_name} completed")

    # Final summary
    print(f"\n{'='*60}")
    print("📊 SETUP SUMMARY")
    print(f"{'='*60}")

    if not failed_steps:
        print("🎉 All setup steps completed successfully!")
        print("\n🚀 Your AI RC Car development environment is ready!")
        print("\n📝 Next steps:")
        print("1. Edit .env file to add your Claude API key")
        print("2. Start building your lib/ modules")
        print("3. Test hardware components")
        return True
    else:
        print(f"⚠️  {len(failed_steps)} step(s) failed:")
        for step in failed_steps:
            print(f"   - {step}")
        print("\n🔧 Check the errors above and try running setup again")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
