from flask import Blueprint ,session, request, jsonify ,send_file
import json
from logger_config import setup_logger
import os
from datetime import datetime, timedelta

logger = setup_logger("logger_module")

logger_bp = Blueprint("logger", __name__)
LOG_DIRECTORY = "logs"

@logger_bp.route('/', methods=['GET'])
def get_logs():
    """
    Get logs with optional filters
    Query params:
    - file: specific log file (default: app.log)
    - lines: number of lines to return (default: 500)
    - level: filter by log level (INFO, WARNING, ERROR, DEBUG)
    - search: search term to filter logs
    """
    try:
        # Get query parameters
        log_file = request.args.get('file', 'app.log')
        lines = int(request.args.get('lines', 500))
        level_filter = request.args.get('level', None)
        search_term = request.args.get('search', None)
        
        # Construct full path
        log_path = os.path.join(LOG_DIRECTORY, log_file)
        
        # Check if file exists
        if not os.path.exists(log_path):
            return jsonify({
                'error': 'Log file not found',
                'available_files': get_available_log_files()
            }), 404
        
        # Read log file
        with open(log_path, 'r', encoding='utf-8') as f:
            # Read last N lines efficiently
            all_lines = f.readlines()
            log_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        # Apply filters
        filtered_logs = []
        for line in log_lines:
            line = line.strip()
            if not line:
                continue
                
            # Level filter
            if level_filter and f'[{level_filter}]' not in line:
                continue
            
            # Search filter
            if search_term and search_term.lower() not in line.lower():
                continue
            
            filtered_logs.append(line)
        
        return jsonify({
            'logs': filtered_logs,
            'total': len(filtered_logs),
            'file': log_file,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@logger_bp.route('/files', methods=['GET'])
def get_log_files():
    """Get list of available log files"""
    try:
        files = get_available_log_files()
        return jsonify({
            'files': files,
            'count': len(files)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@logger_bp.route('/download', methods=['GET'])
def download_log():
    """Download a specific log file"""
    try:
        log_file = request.args.get('file', 'app.log')
        log_path = os.path.join(LOG_DIRECTORY, log_file)
        
        if not os.path.exists(log_path):
            return jsonify({'error': 'Log file not found'}), 404
        
        return send_file(
            log_path,
            as_attachment=True,
            download_name=f'{log_file}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@logger_bp.route('/stats', methods=['GET'])
def get_log_stats():
    """Get statistics about logs"""
    try:
        log_file = request.args.get('file', 'app.log')
        log_path = os.path.join(LOG_DIRECTORY, log_file)
        
        if not os.path.exists(log_path):
            return jsonify({'error': 'Log file not found'}), 404
        
        stats = {
            'INFO': 0,
            'WARNING': 0,
            'ERROR': 0,
            'DEBUG': 0,
            'total': 0
        }
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                stats['total'] += 1
                if '[INFO]' in line:
                    stats['INFO'] += 1
                elif '[WARNING]' in line:
                    stats['WARNING'] += 1
                elif '[ERROR]' in line:
                    stats['ERROR'] += 1
                elif '[DEBUG]' in line:
                    stats['DEBUG'] += 1
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@logger_bp.route('/clear', methods=['POST'])
def clear_logs():
    """Clear a specific log file"""
    try:
        log_file = request.json.get('file', 'app.log')
        log_path = os.path.join(LOG_DIRECTORY, log_file)
        
        if not os.path.exists(log_path):
            return jsonify({'error': 'Log file not found'}), 404
        
        # Clear the file
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write('')
        
        return jsonify({'message': f'Log file {log_file} cleared successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def get_available_log_files():
    """Helper function to get list of log files"""
    if not os.path.exists(LOG_DIRECTORY):
        return []
    
    files = []
    for filename in os.listdir(LOG_DIRECTORY):
        if filename.endswith('.log'):
            file_path = os.path.join(LOG_DIRECTORY, filename)
            file_stat = os.stat(file_path)
            files.append({
                'name': filename,
                'size': file_stat.st_size,
                'modified': datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            })
    
    # Sort by modified time (newest first)
    files.sort(key=lambda x: x['modified'], reverse=True)
    return files
