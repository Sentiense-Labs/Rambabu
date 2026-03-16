#!/usr/bin/env python3
"""
Flask application factory for AI RC Car web dashboard
"""

from flask import Flask
from flask_cors import CORS
from pathlib import Path
from utils.logger import log_info, log_error
import config


def create_app(
    motor=None,
    camera=None,
    ultrasonic=None,
    pan_tilt=None,
    speaker=None,
    mode_manager=None,
):
    """
    Create and configure Flask application

    Args:
        motor: MotorController instance
        camera: Camera instance
        ultrasonic: Ultrasonic instance
        pan_tilt: PanTilt instance
        speaker: Speaker instance
        mode_manager: ModeManager instance

    Returns:
        Flask application instance
    """
    # Create Flask app — use absolute paths so working directory doesn't matter
    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        static_folder=str(project_root / "static"),
        template_folder=str(project_root / "static"),
    )

    # Enable CORS for mobile access
    CORS(app)

    # Register routes blueprint
    from server.routes import routes, set_hardware_dependencies

    app.register_blueprint(routes)

    # Set hardware dependencies
    set_hardware_dependencies(
        motor, camera, ultrasonic, pan_tilt, speaker, mode_manager
    )

    # Configure app
    import os

    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

    # Register error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {"error_code": "NOT_FOUND", "message": "Not found"}, 404

    @app.errorhandler(500)
    def internal_error(error):
        return {"error_code": "INTERNAL_ERROR", "message": "Internal server error"}, 500

    @app.errorhandler(Exception)
    def handle_exception(e):
        log_error(f"Unhandled exception: {e}")
        return {"error_code": "INTERNAL_ERROR", "message": "Internal server error"}, 500

    log_info("Flask application created")
    return app


def run_app(
    motor=None,
    camera=None,
    ultrasonic=None,
    pan_tilt=None,
    speaker=None,
    mode_manager=None,
):
    """
    Run Flask web server

    Args:
        motor: MotorController instance
        camera: Camera instance
        ultrasonic: Ultrasonic instance
        pan_tilt: PanTilt instance
        speaker: Speaker instance
        mode_manager: ModeManager instance
    """
    app = create_app(motor, camera, ultrasonic, pan_tilt, speaker, mode_manager)

    log_info(f"Starting Flask server on {config.FLASK_HOST}:{config.FLASK_PORT}")

    try:
        app.run(
            host=config.FLASK_HOST,
            port=config.FLASK_PORT,
            debug=False,
            threaded=True,
            use_reloader=False,
        )
    except Exception as e:
        log_error(f"Flask server error: {e}")
        raise
