from flask import Blueprint, request, jsonify, session
import pandas as pd
import os
from eligible_stocks import mark_stock_updated
from util import load_stocks_database, save_stocks_database

stock_bp = Blueprint("stock", __name__)

from logger_config import setup_logger

logger = setup_logger("Stock_Module")


# ==================== HELPER FUNCTIONS ====================

# ==================== API ENDPOINTS ====================


@stock_bp.route('/add-stock', methods=['POST'])
def add_stock():
    try:
        if not session.get('logged_in'):
            return jsonify({'success': False,'error': 'Not logged in'}), 401
        
        data = request.json
        symbol = data.get('symbol')
        instrument_token = data.get('instrument_token')
        high = data.get('high')     
        low = data.get('low')
        date_str = data.get('date')          
        # Validate required fields
        if not all([symbol, instrument_token, high, low, date_str]):
            return jsonify({'success': False,'error': 'All fields are required: symbol, instrument_token, high, low, date'}), 400
        
        # Load existing database
        df = load_stocks_database()
        
        # Check if stock already exists for this date
        existing = df[(df['symbol'] == symbol) & (df['date'] == date_str)]
        
        if not existing.empty:
            # Update existing record
            df.loc[(df['symbol'] == symbol) & (df['date'] == date_str), ['instrument_token', 'high', 'low']] = [
                instrument_token, float(high), float(low)
            ]
            message = f'Stock {symbol} updated for {date_str}'
        else:
            # Add new record
            new_row = pd.DataFrame([{
                'symbol': symbol,
                'instrument_token': int(instrument_token),
                'high': float(high),
                'low': float(low),
                'date': date_str
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            message = f'Stock {symbol} added for {date_str}'
        


        # Save to Excel
        save_stocks_database(df)
        mark_stock_updated()
        
        return jsonify({
            'success': True,
            'message': message,
            'stock': {
                'symbol': symbol,
                'instrument_token': instrument_token,
                'high': high,
                'low': low,
                'date': date_str
            }
        })
        
    except Exception as e:
        logger.exception("Error in Add Stock")
        return jsonify({
            'success': False,
            'error': f'Failed to add stock: {str(e)}'
        }), 500

@stock_bp.route('/get-stocks', methods=['GET'])
def get_stocks():
    """Get all stocks or stocks for a specific date"""
    try:
        if not session.get('logged_in'):
            return jsonify({'success': False,'error': 'Not logged in'}), 401
        
        date_filter = request.args.get('date')  # Optional date filter
        
        df = load_stocks_database()
        
        if df.empty:
            return jsonify({'success': True,'stocks': [],'count': 0})
        
        # Filter by date if provided
        if date_filter:
            df = df[df['date'] == date_filter]
        
        # Convert to list of dictionaries
        stocks = df.to_dict('records')
        
        return jsonify({'success': True,'stocks': stocks,'count': len(stocks)})
        
    except Exception as e:
        logger.exception("Error in Get Stocks")
        return jsonify({'success': False,'error': f'Failed to fetch stocks: {str(e)}'}), 500

@stock_bp.route('/delete-stock', methods=['POST'])
def delete_stock():
    """Delete a stock from database"""
    try:
        if not session.get("logged_in"):
            return jsonify({"success": False, "error": "Not logged in"}), 401
        
        data = request.json
        symbol = data.get('symbol')
        date_str = data.get('date')
        
        if not symbol or not date_str:
            return jsonify({
                'success': False,
                'error': 'Symbol and date are required'
            }), 400
        
        df = load_stocks_database()
        
        # Remove the stock
        df = df[~((df['symbol'] == symbol) & (df['date'] == date_str))]
        
        save_stocks_database(df)
        mark_stock_updated()
        return jsonify({
            'success': True,
            'message': f'Stock {symbol} deleted for {date_str}'
        })
        
    except Exception as e:
        logger.exception("Error in Deleting Stocks")
        return jsonify({
            'success': False,
            'error': f'Failed to delete stock: {str(e)}'
        }), 500

@stock_bp.route('/update-stock', methods=['POST'])
def update_stock():
    """Update an existing stock (by symbol + date)"""
    try:
        if not session.get("logged_in"):
            return jsonify({"success": False, "error": "Not logged in"}), 401
        
        data = request.get_json()

        required_fields = ['symbol', 'date', 'high', 'low', 'instrument_token']
        missing = [f for f in required_fields if f not in data]

        if missing:
            return jsonify({
                'success': False,
                'error': f'Missing fields: {", ".join(missing)}'
            }), 400

        # Use original identifiers if provided (for when symbol/date changes)
        search_symbol = data.get('original_symbol', data['symbol'])
        search_date = data.get('original_date', data['date'])
        
        # New values to update
        new_symbol = data['symbol']
        new_date = data['date']

        df = load_stocks_database()

        if df.empty:
            return jsonify({
                'success': False,
                'error': 'Stock database is empty'
            }), 404

        # Find stock row using ORIGINAL identifiers
        mask = (df['symbol'] == search_symbol) & (df['date'] == search_date)

        if not mask.any():
            return jsonify({
                'success': False,
                'error': f'Stock {search_symbol} not found for {search_date}'
            }), 404

        # Update ALL values including symbol and date
        df.loc[mask, 'symbol'] = new_symbol
        df.loc[mask, 'date'] = new_date
        df.loc[mask, 'high'] = float(data['high'])
        df.loc[mask, 'low'] = float(data['low'])
        df.loc[mask, 'instrument_token'] = data['instrument_token']

        save_stocks_database(df)
        mark_stock_updated()
        return jsonify({
            'success': True,
            'message': f'{new_symbol} updated successfully'
        })

    except Exception as e:
        logger.exception("Error In Update Stock")
        return jsonify({
            'success': False,
            'error': f'Failed to update stock: {str(e)}'
        }), 500  