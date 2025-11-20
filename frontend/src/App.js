import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import axios from "axios";
import "@/App.css";
import "@/index.css";
import { Toaster } from "@/components/ui/toaster.jsx";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button.jsx";
import { Input } from "@/components/ui/input.jsx";
import { Textarea } from "@/components/ui/textarea.jsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select.jsx";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card.jsx";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

axios.defaults.baseURL = API;

function useCitiesAndCategories() {
  const [cities, setCities] = React.useState([]);
  const [categories, setCategories] = React.useState([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    async function load() {
      try {
        const [cRes, sRes] = await Promise.all([
          axios.get("/meta/cities"),
          axios.get("/meta/service-categories"),
        ]);
        setCities(cRes.data);
        setCategories(sRes.data);
      } catch (err) {
        console.error("Failed to load meta", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return { cities, categories, loading };
}

function ClientHomePage() {
  const { toast } = useToast();
  const { cities, categories, loading } = useCitiesAndCategories();
  const [form, setForm] = React.useState({
    city_slug: "",
    service_category_slug: "",
    title: "",
    description: "",
    zip: "",
    preferred_timing: "flexible",
    client_name: "",
    client_phone: "",
    client_email: "",
    is_test: false,
  });
  const [submitting, setSubmitting] = React.useState(false);
  const [statusLink, setStatusLink] = React.useState(null);

  const onChange = (field) => (e) => {
    const value = e?.target ? (e.target.type === "checkbox" ? e.target.checked : e.target.value) : e;
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        client_email: form.client_email || undefined,
      };
      const res = await axios.post("/jobs", payload);
      const { job_id, client_view_token } = res.data;
      const link = `/jobs/${job_id}/status?token=${encodeURIComponent(client_view_token)}`;
      setStatusLink(link);
      toast({
        title: "Request received",
        description: "We logged your job. You can track it from the status link.",
      });
    } catch (err) {
      console.error("Job create error", err);
      toast({
        title: "There was a problem",
        description: "Please check your details and try again.",
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <div className="app-header-title">The Bridge — Local Services</div>
          <div className="app-tagline">A local operator routing trusted pros in your city.</div>
        </div>
        <div className="app-header-badge">Albuquerque first · Built for multi-city</div>
      </header>

      <main className="app-main">
        <section>
          <div className="app-hero-title" data-testid="hero-main-title">
            Local help, routed by a real human operator.
          </div>
          <p className="app-hero-subtitle" data-testid="hero-subtitle">
            Tell us what you need in a few fields. We&apos;ll match you with a vetted contractor and keep you updated from quote to completion.
          </p>
          <div className="app-hero-chip-row">
            <span className="app-hero-chip" data-testid="chip-city">Starting in Albuquerque</span>
            <span className="app-hero-chip" data-testid="chip-handyman">Handyman & cleaning first</span>
            <span className="app-hero-chip" data-testid="chip-operator">Operator-managed quotes & dispatch</span>
          </div>

          <div className="app-secondary-surface" data-testid="info-sandbox">
            <strong>Sandbox-friendly.</strong> Flip on the test toggle in the form and your job is clearly marked as a test so it doesn&apos;t pollute real metrics.
          </div>
        </section>

        <section>
          <div className="app-panel" data-testid="client-job-request-panel">
            <div className="app-panel-header">
              <div>
                <div className="app-panel-title">Request local help</div>
                <div className="app-panel-subtitle">Answer a few questions so we can route your job.</div>
              </div>
              <span className="app-badge-soft" data-testid="badge-response-time">Typical response in &lt; 15 minutes</span>
            </div>

            <form onSubmit={handleSubmit} className="space-y-3" data-testid="job-request-form">
              <div className="app-input-row">
                <div>
                  <label className="text-xs text-slate-300" htmlFor="city" data-testid="label-city">
                    City
                  </label>
                  <Select
                    onValueChange={(v) => onChange("city_slug")({ target: { value: v } })}
                    value={form.city_slug}
                  >
                    <SelectTrigger id="city" data-testid="input-city">
                      <SelectValue placeholder={loading ? "Loading cities..." : "Choose city"} />
                    </SelectTrigger>
                    <SelectContent>
                      {cities.map((c) => (
                        <SelectItem key={c.id} value={c.slug} data-testid={`input-city-option-${c.slug}`}>
                          {c.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <label className="text-xs text-slate-300" htmlFor="category" data-testid="label-category">
                    Service category
                  </label>
                  <Select
                    onValueChange={(v) => onChange("service_category_slug")({ target: { value: v } })}
                    value={form.service_category_slug}
                  >
                    <SelectTrigger id="category" data-testid="input-category">
                      <SelectValue placeholder={loading ? "Loading categories..." : "Choose service"} />
                    </SelectTrigger>
                    <SelectContent>
                      {categories.map((s) => (
                        <SelectItem key={s.id} value={s.slug} data-testid={`input-category-option-${s.slug}`}>
                          {s.display_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div>
                <label className="text-xs text-slate-300" htmlFor="title" data-testid="label-title">
                  Short title (optional)
                </label>
                <Input
                  id="title"
                  data-testid="input-title"
                  placeholder="e.g. Hang 2 shelves and a mirror"
                  value={form.title}
                  onChange={onChange("title")}
                />
              </div>

              <div>
                <label className="text-xs text-slate-300" htmlFor="description" data-testid="label-description">
                  What do you need done?
                </label>
                <Textarea
                  id="description"
                  data-testid="input-description"
                  placeholder="Share enough detail for a clear quote — room, materials, constraints."
                  rows={4}
                  value={form.description}
                  onChange={onChange("description")}
                />
              </div>

              <div className="app-input-row">
                <div>
                  <label className="text-xs text-slate-300" htmlFor="zip" data-testid="label-zip">
                    ZIP code
                  </label>
                  <Input
                    id="zip"
                    data-testid="input-zip"
                    placeholder="e.g. 87101"
                    value={form.zip}
                    onChange={onChange("zip")}
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-300" htmlFor="timing" data-testid="label-preferred-timing">
                    Preferred timing
                  </label>
                  <Select
                    onValueChange={(v) => onChange("preferred_timing")({ target: { value: v } })}
                    value={form.preferred_timing}
                  >
                    <SelectTrigger id="timing" data-testid="input-preferred-timing">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="asap" data-testid="input-preferred-timing-asap">
                        ASAP
                      </SelectItem>
                      <SelectItem value="today" data-testid="input-preferred-timing-today">
                        Today
                      </SelectItem>
                      <SelectItem value="this_week" data-testid="input-preferred-timing-this_week">
                        This week
                      </SelectItem>
                      <SelectItem value="flexible" data-testid="input-preferred-timing-flexible">
                        Flexible
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="app-divider-label">How can we reach you?</div>
              <div className="app-input-row">
                <div>
                  <label className="text-xs text-slate-300" htmlFor="client_name" data-testid="label-client-name">
                    Name
                  </label>
                  <Input
                    id="client_name"
                    data-testid="input-client-name"
                    value={form.client_name}
                    onChange={onChange("client_name")}
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-300" htmlFor="client_phone" data-testid="label-client-phone">
                    Mobile number
                  </label>
                  <Input
                    id="client_phone"
                    data-testid="input-client-phone"
                    placeholder="We&apos;ll text scheduling details later."
                    value={form.client_phone}
                    onChange={onChange("client_phone")}
                  />
                </div>
              </div>

              <div>
                <label className="text-xs text-slate-300" htmlFor="client_email" data-testid="label-client-email">
                  Email (optional, for receipts)
                </label>
                <Input
                  id="client_email"
                  data-testid="input-client-email"
                  type="email"
                  value={form.client_email}
                  onChange={onChange("client_email")}
                />
              </div>

              <div className="flex items-center justify-between gap-3 pt-1">
                <label className="flex items-center gap-2 text-xs text-slate-300" data-testid="label-is-test">
                  <input
                    type="checkbox"
                    checked={form.is_test}
                    onChange={onChange("is_test")}
                    className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-900"
                    data-testid="input-is-test-toggle"
                  />
                  <span>This is a sandbox / test job</span>
                </label>
                <span className="app-badge-soft-warm" data-testid="badge-no-app">
                  No app to install, just a link.
                </span>
              </div>

              <div className="flex items-center justify-between pt-3">
                <Button
                  type="submit"
                  className="app-primary-button"
                  disabled={submitting}
                  data-testid="job-request-submit-button"
                >
                  {submitting ? "Submitting..." : "Send request"}
                </Button>

                {statusLink && (
                  <a
                    href={statusLink}
                    className="app-ghost-button"
                    data-testid="job-status-link"
                  >
                    Open status page
                  </a>
                )}
              </div>

              <p className="app-footer-note" data-testid="privacy-note">
                We&apos;ll only use your contact info for this job and essential updates. Payment is handled securely via Stripe in test mode for now.
              </p>
            </form>
          </div>
        </section>
      </main>
      <Toaster />
    </div>
  );
}

function PlaceholderPage({ title }) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-title">{title}</div>
      </header>
      <main className="app-main">
        <Card className="w-full max-w-xl" data-testid="placeholder-card">
          <CardHeader>
            <CardTitle>{title}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-500" data-testid="placeholder-text">
              This view will be fleshed out next: routing to jobs, quotes, and contractor tools. Core backend flows are being wired first so manual testing is easy.
            </p>
          </CardContent>
        </Card>
      </main>
      <Toaster />
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ClientHomePage />} />
        <Route path="/jobs/:jobId/status" element={<PlaceholderPage title="Job status" />} />
        <Route path="/contractor/*" element={<PlaceholderPage title="Contractor portal" />} />
        <Route path="/operator/*" element={<PlaceholderPage title="Operator dashboard" />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
