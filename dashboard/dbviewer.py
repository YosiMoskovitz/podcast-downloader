from flask import Blueprint, render_template, request, flash
import os
from db_helper import get_connection

bp = Blueprint('dbviewer', __name__, template_folder='templates')

@bp.route('/db')
def db_viewer():
    tables = []
    table_data = {}
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # PostgreSQL query for table names
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]

        # Sanitize and pick selected table
        selected = request.args.get('table', tables[0] if tables else None)
        if selected not in tables:
            selected = tables[0] if tables else None

        # Pagination params
        try:
            page = max(1, int(request.args.get('page', 1)))
        except Exception:
            page = 1
        try:
            per_page = int(request.args.get('per_page', 25))
            if per_page <= 0:
                per_page = 25
        except Exception:
            per_page = 25

        if selected:
            # Total rows
            cursor.execute(f"SELECT COUNT(*) FROM {selected}")
            total_rows = cursor.fetchone()[0]

            total_pages = max(1, (total_rows + per_page - 1) // per_page)
            if page > total_pages:
                page = total_pages

            offset = (page - 1) * per_page
            # Retrieve limited rows for current page (PostgreSQL uses LIMIT/OFFSET)
            cursor.execute(f'SELECT * FROM {selected} LIMIT %s OFFSET %s', (per_page, offset))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            table_data = {
                'name': selected,
                'columns': columns,
                'rows': rows,
                'total_rows': total_rows,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages
            }
            # compute sliding window for pagination to avoid template-side Python builtins
            start_page = 1 if page - 3 < 1 else page - 3
            end_page = total_pages if page + 3 > total_pages else page + 3
            table_data['start_page'] = start_page
            table_data['end_page'] = end_page
        conn.close()
    except Exception as e:
        flash(f'Error reading database: {e}')
    return render_template('dbviewer.html', tables=tables, table_data=table_data)
