from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/membership')
def membership():
    return render_template('membership.html')

@app.route('/about')
def about():
    return "<h1>About VRS Library</h1><p>Work in progress...</p>"

@app.route('/renew')
def renew():
    return "<h1>Renew Membership</h1><p>Work in progress...</p>"

if __name__ == '__main__':
    app.run(debug=True, port=9090)
