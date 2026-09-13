"use client";

import { useEffect, useState } from "react";
import {
  CheckCircle2,
  CircleAlert,
  Info,
  Key,
  Loader2,
  Moon,
  Server,
  Sun,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useTheme } from "@/components/theme-provider";
import { providerStatus, type ProviderStatus } from "@/lib/v1";

const PROVIDERS = [
  { id: "openai", label: "OpenAI", color: "text-emerald-400", url: "https://platform.openai.com/api-keys" },
  { id: "anthropic", label: "Anthropic", color: "text-orange-400", url: "https://console.anthropic.com/settings/keys" },
  { id: "google", label: "Google", color: "text-blue-400", url: "https://aistudio.google.com/app/apikey" },
  { id: "deepseek", label: "DeepSeek", color: "text-indigo-400", url: "https://platform.deepseek.com/api_keys" },
  { id: "xai", label: "xAI", color: "text-gray-400", url: "https://console.x.ai" },
  { id: "moonshot", label: "Moonshot", color: "text-red-400", url: "https://platform.moonshot.ai" },
  { id: "mistral", label: "Mistral", color: "text-cyan-400", url: "https://console.mistral.ai/api-keys" },
  { id: "ollama", label: "Ollama", color: "text-purple-400", url: "https://ollama.com" },
];

export default function SettingsPage() {
  const { theme, toggleTheme } = useTheme();
  const [providers, setProviders] = useState<ProviderStatus | null>(null);
  const [providerError, setProviderError] = useState<string | null>(null);

  useEffect(() => {
    providerStatus()
      .then(setProviders)
      .catch((error: Error) => setProviderError(error.message));
  }, []);

  return (
    <div className="space-y-8 max-w-2xl animate-fade-in">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground mt-1">Provider readiness and workbench preferences.</p>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          {theme === "dark" ? <Moon className="h-4 w-4 text-primary" /> : <Sun className="h-4 w-4 text-primary" />}
          Appearance
        </h2>
        <Card>
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="font-medium text-sm">Theme</p>
              <p className="text-xs text-muted-foreground mt-0.5">Currently using <strong>{theme}</strong> mode</p>
            </div>
            <Button variant="outline" size="sm" onClick={toggleTheme} className="gap-2">
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              Switch to {theme === "dark" ? "Light" : "Dark"}
            </Button>
          </CardContent>
        </Card>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Key className="h-4 w-4 text-primary" />LLM Providers
        </h2>
        <p className="text-xs text-muted-foreground">
          Credentials stay in the backend environment. This page reports only whether a
          provider is configured; secret values are never sent to the browser.
        </p>

        <div className="space-y-3">
          {PROVIDERS.map(provider => {
            const status = providers?.providers.find(item => item.id === provider.id);
            return (
              <Card key={provider.id}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className={`font-semibold text-sm ${provider.color}`}>{provider.label}</p>
                      <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1.5">
                        {!providers && !providerError ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : status?.configured ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                        ) : (
                          <CircleAlert className="h-3.5 w-3.5 text-amber-500" />
                        )}
                        {!providers && !providerError
                          ? "Checking server…"
                          : status?.configured
                            ? "Configured on server"
                            : "Not configured"}
                      </p>
                    </div>
                    <a
                      href={provider.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-primary hover:underline shrink-0"
                    >
                      Provider setup →
                    </a>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        <div className="rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
          {providerError ? (
            <><strong>Status unavailable:</strong> {providerError}</>
          ) : (
            <><strong>Secure setup:</strong> set provider variables in the backend process,
            secret manager, or Docker Compose environment, then restart the backend.</>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Server className="h-4 w-4 text-primary" />Runtime
        </h2>
        <Card>
          <CardContent className="p-4 space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-muted-foreground">API</span><span className="font-medium">Stable /v1 surface</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Credential boundary</span><span className="font-medium">Server only</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Configured providers</span><span className="font-medium">{providers ? `${providers.configured} of ${providers.total}` : "Not checked"}</span></div>
          </CardContent>
        </Card>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Info className="h-4 w-4 text-primary" />About
        </h2>
        <Card>
          <CardContent className="p-4 space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-muted-foreground">Version</span><span className="font-mono font-medium">1.0.0</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">License</span><span className="font-medium">MIT</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">GitHub</span>
              <a href="https://github.com/BaijayantaRoy/Assay" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline font-medium">View source →</a>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
