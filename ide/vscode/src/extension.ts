import * as http from "http";
import * as https from "https";
import * as vscode from "vscode";

type BgiResult = {
    unit_id: string;
    name: string;
    file_path: string;
    score: number;
    reasoning: string;
    is_exported: boolean;
};

type BgiResponse = {
    query: string;
    count: number;
    results: BgiResult[];
};

function getConfig() {
    const config = vscode.workspace.getConfiguration("bgiSearch");
    const apiBaseUrl = config.get<string>("apiBaseUrl", "http://127.0.0.1:8000");
    const maxResults = config.get<number>("maxResults", 10);
    return { apiBaseUrl, maxResults };
}

function fetchJson(url: string): Promise<BgiResponse> {
    return new Promise((resolve, reject) => {
        const parsed = new URL(url);
        const lib = parsed.protocol === "https:" ? https : http;

        const req = lib.request(
            {
                method: "GET",
                hostname: parsed.hostname,
                port: parsed.port,
                path: `${parsed.pathname}${parsed.search}`,
                timeout: 3000,
            },
            (res) => {
                if ((res.statusCode ?? 500) >= 400) {
                    reject(new Error(`BGI API request failed (${res.statusCode ?? 500})`));
                    return;
                }

                let data = "";
                res.on("data", (chunk) => {
                    data += chunk;
                });
                res.on("end", () => {
                    try {
                        resolve(JSON.parse(data) as BgiResponse);
                    } catch {
                        reject(new Error("BGI API returned invalid JSON"));
                    }
                });
            }
        );

        req.on("error", (err) => reject(err));
        req.on("timeout", () => req.destroy(new Error("BGI API request timed out")));
        req.end();
    });
}

async function showResults(response: BgiResponse): Promise<void> {
    if (response.count === 0) {
        vscode.window.showInformationMessage("BGI: no matches found.");
        return;
    }

    const picks = response.results.map((result) => ({
        label: `${result.name} (${result.score.toFixed(2)})`,
        description: result.reasoning,
        detail: `${result.file_path} • ${result.unit_id}`,
        result,
    }));

    const selected = await vscode.window.showQuickPick(picks, {
        title: "BGI Search Results",
        matchOnDescription: true,
        matchOnDetail: true,
    });

    if (!selected) {
        return;
    }

    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
        vscode.window.showWarningMessage("BGI: open a workspace to jump to files.");
        return;
    }

    const targetUri = vscode.Uri.joinPath(workspaceFolder.uri, selected.result.file_path);
    try {
        const doc = await vscode.workspace.openTextDocument(targetUri);
        await vscode.window.showTextDocument(doc, { preview: false });
    } catch {
        vscode.window.showWarningMessage(`BGI: could not open ${selected.result.file_path}`);
    }
}

async function runQuery(endpoint: string): Promise<void> {
    const { apiBaseUrl } = getConfig();
    const url = `${apiBaseUrl}${endpoint}`;

    try {
        const response = await fetchJson(url);
        await showResults(response);
    } catch (err) {
        const message = err instanceof Error ? err.message : "unknown error";
        vscode.window.showErrorMessage(`BGI query failed: ${message}`);
    }
}

export function activate(context: vscode.ExtensionContext) {
    context.subscriptions.push(
        vscode.commands.registerCommand("bgi.lookupSymbol", async () => {
            const symbol = await vscode.window.showInputBox({
                title: "BGI Lookup Symbol",
                prompt: "Enter exact symbol name (e.g. fetch_user)",
                ignoreFocusOut: true,
            });
            if (!symbol) {
                return;
            }

            const { maxResults } = getConfig();
            const endpoint = `/api/symbols/${encodeURIComponent(symbol)}?max_results=${maxResults}`;
            await runQuery(endpoint);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand("bgi.searchPrefix", async () => {
            const query = await vscode.window.showInputBox({
                title: "BGI Search Prefix",
                prompt: "Enter prefix (e.g. fetch)",
                ignoreFocusOut: true,
            });
            if (!query) {
                return;
            }

            const { maxResults } = getConfig();
            const endpoint = `/api/search?q=${encodeURIComponent(query)}&max_results=${maxResults}`;
            await runQuery(endpoint);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand("bgi.findCallers", async () => {
            const symbol = await vscode.window.showInputBox({
                title: "BGI Find Callers",
                prompt: "Enter symbol name (e.g. fetch_user)",
                ignoreFocusOut: true,
            });
            if (!symbol) {
                return;
            }

            const { maxResults } = getConfig();
            const endpoint = `/api/callers/${encodeURIComponent(symbol)}?max_results=${maxResults}`;
            await runQuery(endpoint);
        })
    );
}

export function deactivate() {
    // No long-lived resources in prototype.
}
