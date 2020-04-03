from flask import Flask, render_template, flash
from config import Config
from compare import Compare

app = Flask(__name__)
app.config.from_object(Config)

@app.route('/')
@app.route('/index')
def root():
    return render_template('index.html', title='Home')

@app.route('/compare', methods=['GET','POST'])
def webcompare():
    return Compare().compare()


if __name__ == '__main__':
    # This is used when running locally only. When deploying to Google App
    # Engine, a webserver process such as Gunicorn will serve the app. This
    # can be configured by adding an `entrypoint` to app.yaml.
    # Flask's development server will automatically serve static files in
    # the "static" directory. See:
    # http://flask.pocoo.org/docs/1.0/quickstart/#static-files. Once deployed,
    # App Engine itself will serve those files as configured in app.yaml.
    app.run(host='127.0.0.1', port=5000, debug=True)