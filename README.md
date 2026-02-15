#### 🔧 Set Up the Environment - Client

1. **Clone the Repository**

```bash
git clone https://github.com/ZahrizhalAli/lokin.git
cd lokin
```

2. **Build the Client**

The Python package serves a built React client, so you need to build it first:

```bash
cd client
npm install
npm run build
cd ..
```

This creates the `client/dist/` directory that the Python package will serve.

3. **Try the Sample App**

Now you can test the local package with the sample app:

```bash
uv sync  # Installs dependencies and the local package in editable mode
uv run app.py
```

Then open http://localhost:7860 in your browser.
