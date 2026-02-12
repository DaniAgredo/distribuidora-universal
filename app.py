from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def inicio():
    return render_template("index.html")

@app.route("/conocenos")
def conocenos():
    return render_template("conocenos.html")

@app.route("/envios")
def envios():
    return render_template("envios.html")

@app.route("/devoluciones")
def devoluciones():
    return render_template("devoluciones.html")

@app.route("/pagos")
def pagos():
    return render_template("pagos.html")

@app.route("/cuenta")
def cuenta():
    return render_template("cuenta.html")

if __name__ == "__main__":
    app.run(debug=True)

