from app import app

with app.test_client() as c:
    try:
        resp = c.get('/')
        print('STATUS', resp.status_code)
        print(resp.get_data(as_text=True)[:2000])
    except Exception as e:
        import traceback
        traceback.print_exc()
        print('EXC', e)
