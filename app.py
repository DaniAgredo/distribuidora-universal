from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def inicio():
    return render_template("index.html")

@app.route("/conocenos")
def conocenos():
    return render_template("conocenos.html")

if __name__ == "__main__":
    app.run(debug=True)

