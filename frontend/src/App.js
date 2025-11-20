import React from "react";
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useSearchParams, useParams } from "react-router-dom";
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

function JobStatusPage() {
  const { toast } = useToast();
  const { jobId } = useParams();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const [loading, setLoading] = React.useState(true);
  const [approving, setApproving] = React.useState(false);
  const [job, setJob] = React.useState(null);

  React.useEffect(() => {
    async function load() {
      if (!jobId || !token) return;
      try {
        const res = await axios.get(`/jobs/${jobId}/status`, { params: { token } });
        setJob(res.data);
      } catch (err) {
        console.error("Failed to load job status", err);
        toast({
          title: "Unable to load job",
          description: "The status link may be invalid or expired.",
        });
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [jobId, token, toast]);

  async function handleApproveAndPay() {
    if (!jobId || !token) return;
    setApproving(true);
    try {
      const res = await axios.post(`/jobs/${jobId}/approve-quote`, { token });
      const { checkout_url: checkoutUrl } = res.data;
      if (checkoutUrl) {
        window.location.href = checkoutUrl;
      } else {
        toast({
          title: "Quote approved",
          description: "Your job is confirmed.",
        });
      }
    } catch (err) {
      console.error("approve-quote failed", err);
      toast({
        title: "Could not approve quote",
        description: "Please refresh the page or contact the operator.",
      });
    } finally {
      setApproving(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <div className="app-header-title">Job status</div>
          <div className="app-tagline">Track this request from quote to payout.</div>
        </div>
      </header>
      <main className="app-main">
        <section>
          <Card data-testid="job-status-card">
            <CardHeader>
              <CardTitle className="text-base">Client view</CardTitle>
            </CardHeader>
            <CardContent>
              {loading && <p data-testid="job-status-loading">Loading job details…</p>}
              {!loading && !job && (
                <p className="text-sm text-slate-500" data-testid="job-status-error">
                  We couldn&apos;t find this job. Double-check your link.
                </p>
              )}
              {!loading && job && (
                <div className="space-y-3" data-testid="job-status-summary">
                  <div>
                    <div className="text-xs text-slate-500">Job</div>
                    <div className="text-sm font-medium" data-testid="job-status-title">
                      {job.title || "Untitled request"}
                    </div>
                    <p className="mt-1 text-xs text-slate-500" data-testid="job-status-description">
                      {job.description}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className="px-2 py-1 rounded-full bg-slate-100 text-slate-700" data-testid="job-status-badge">
                      Status: {job.status}
                    </span>
                    {job.quote_status && (
                      <span className="px-2 py-1 rounded-full bg-emerald-50 text-emerald-700" data-testid="job-quote-status-badge">
                        Quote: {job.quote_status}
                      </span>
                    )}
                    {job.payment_status && (
                      <span className="px-2 py-1 rounded-full bg-indigo-50 text-indigo-700" data-testid="job-payment-status-badge">
                        Payment: {job.payment_status}
                      </span>
                    )}
                  </div>
                  {job.quote_total_cents != null && (
                    <div className="border-t border-slate-200 pt-3 mt-2">
                      <div className="text-xs text-slate-500">Quote total</div>
                      <div className="text-lg font-semibold" data-testid="job-quote-total">
                        ${(job.quote_total_cents / 100).toFixed(2)} USD
                      </div>
                    </div>
                  )}
                  {job.quote_status === "sent_to_client" && job.status === "quote_sent" && (
                    <div className="pt-2">
                      <Button
                        onClick={handleApproveAndPay}
                        disabled={approving}
                        data-testid="approve-and-pay-button"
                      >
                        {approving ? "Opening checkout…" : "Approve & pay with Stripe"}
                      </Button>
                      <p className="mt-1 text-[11px] text-slate-500" data-testid="approve-and-pay-note">
                        You&apos;ll be redirected to a secure Stripe Checkout page in test mode.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      </main>
      <Toaster />
    </div>
  );
}

function AuthForm({ title, onSubmit, submitting, dataTestIdPrefix }) {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");

  function handleSubmit(e) {
    e.preventDefault();
    onSubmit({ email, password });
  }

  return (
    <Card className="w-full max-w-sm" data-testid={`${dataTestIdPrefix}-card`}>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3" data-testid={`${dataTestIdPrefix}-form`}>
          <div>
            <label className="text-xs text-slate-600" htmlFor={`${dataTestIdPrefix}-email`}>
              Email
            </label>
            <Input
              id={`${dataTestIdPrefix}-email`}
              data-testid={`${dataTestIdPrefix}-email-input`}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-slate-600" htmlFor={`${dataTestIdPrefix}-password`}>
              Password
            </label>
            <Input
              id={`${dataTestIdPrefix}-password`}
              data-testid={`${dataTestIdPrefix}-password-input`}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <Button
            type="submit"
            disabled={submitting}
            data-testid={`${dataTestIdPrefix}-submit-button`}
          >
            {submitting ? "Signing in..." : "Sign in"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function useAuth(roleKey) {
  const [token, setToken] = React.useState(() => localStorage.getItem(roleKey) || "");

  function saveToken(nextToken) {
    setToken(nextToken);
    if (nextToken) {
      localStorage.setItem(roleKey, nextToken);
    } else {
      localStorage.removeItem(roleKey);
    }
  }

  return { token, saveToken };
}

function OperatorLoginPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { token, saveToken } = useAuth("operator_jwt");
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (token) {
      navigate("/operator/dashboard", { replace: true });
    }
  }, [token, navigate]);

  async function handleLogin({ email, password }) {
    setSubmitting(true);
    try {
      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", password);
      const res = await axios.post("/auth/login", formData, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      saveToken(res.data.access_token);
      navigate("/operator/dashboard", { replace: true });
    } catch (err) {
      console.error("Operator login failed", err);
      toast({ title: "Login failed", description: "Check your credentials and role." });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-title">Operator login</div>
      </header>
      <main className="app-main">
        <section>
          <AuthForm
            title="Sign in as operator/admin"
            onSubmit={handleLogin}
            submitting={submitting}
            dataTestIdPrefix="operator-login"
          />
        </section>
      </main>
      <Toaster />
    </div>
  );
}

function OperatorDashboard() {
  const { toast } = useToast();
  const { token } = useAuth("operator_jwt");
  const navigate = useNavigate();
  const [filters, setFilters] = React.useState({ city_slug: "", status: "", service_category_slug: "" });
  const [jobs, setJobs] = React.useState([]);
  const { cities, categories } = useCitiesAndCategories();

  React.useEffect(() => {
    if (!token) {
      navigate("/operator/login", { replace: true });
    }
  }, [token, navigate]);

  React.useEffect(() => {
    async function load() {
      try {
        const params = {};
        if (filters.city_slug) params.city_slug = filters.city_slug;
        if (filters.status) params.status = filters.status;
        if (filters.service_category_slug) params.service_category_slug = filters.service_category_slug;
        const res = await axios.get("/operator/jobs", {
          params,
          headers: { Authorization: `Bearer ${token}` },
        });
        setJobs(res.data);
      } catch (err) {
        console.error("Failed to load jobs", err);
        toast({ title: "Could not load jobs", description: "Check your operator access." });
      }
    }
    if (token) load();
  }, [filters, token, toast]);

  return (
    <div className="app-shell" data-testid="operator-dashboard">
      <header className="app-header">
        <div>
          <div className="app-header-title">Operator dashboard</div>
          <div className="app-tagline">Watch jobs flow through the money loop.</div>
        </div>
      </header>
      <main className="app-main">
        <section className="space-y-3">
          <div className="flex flex-wrap gap-2" data-testid="operator-filters">
            <Select
              value={filters.city_slug}
              onValueChange={(v) => setFilters((f) => ({ ...f, city_slug: v }))}
            >
              <SelectTrigger className="w-40" data-testid="operator-filter-city">
                <SelectValue placeholder="All cities" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="" data-testid="operator-filter-city-all">All cities</SelectItem>
                {cities.map((c) => (
                  <SelectItem key={c.id} value={c.slug} data-testid={`operator-filter-city-${c.slug}`}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select
              value={filters.service_category_slug}
              onValueChange={(v) => setFilters((f) => ({ ...f, service_category_slug: v }))}
            >
              <SelectTrigger className="w-44" data-testid="operator-filter-category">
                <SelectValue placeholder="All services" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="" data-testid="operator-filter-category-all">All services</SelectItem>
                {categories.map((s) => (
                  <SelectItem key={s.id} value={s.slug} data-testid={`operator-filter-category-${s.slug}`}>
                    {s.display_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select
              value={filters.status}
              onValueChange={(v) => setFilters((f) => ({ ...f, status: v }))}
            >
              <SelectTrigger className="w-44" data-testid="operator-filter-status">
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="" data-testid="operator-filter-status-all">All</SelectItem>
                <SelectItem value="new" data-testid="operator-filter-status-new">New</SelectItem>
                <SelectItem value="offering_contractors" data-testid="operator-filter-status-offering">Offering</SelectItem>
                <SelectItem value="awaiting_quote" data-testid="operator-filter-status-awaiting-quote">Awaiting quote</SelectItem>
                <SelectItem value="quote_sent" data-testid="operator-filter-status-quote-sent">Quote sent</SelectItem>
                <SelectItem value="awaiting_payment" data-testid="operator-filter-status-awaiting-payment">Awaiting payment</SelectItem>
                <SelectItem value="confirmed" data-testid="operator-filter-status-confirmed">Confirmed</SelectItem>
                <SelectItem value="completed" data-testid="operator-filter-status-completed">Completed</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <Card data-testid="operator-jobs-card">
            <CardHeader>
              <CardTitle className="text-base">Jobs</CardTitle>
            </CardHeader>
            <CardContent>
              {jobs.length === 0 ? (
                <p className="text-sm text-slate-500" data-testid="operator-jobs-empty">
                  No jobs match your filters yet.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-xs" data-testid="operator-jobs-table">
                    <thead className="border-b border-slate-200 text-[11px] uppercase text-slate-500">
                      <tr>
                        <th className="px-2 py-1 text-left">Created</th>
                        <th className="px-2 py-1 text-left">Title</th>
                        <th className="px-2 py-1 text-left">City</th>
                        <th className="px-2 py-1 text-left">Category</th>
                        <th className="px-2 py-1 text-left">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobs.map((j) => (
                        <tr key={j.id} className="border-b border-slate-100" data-testid={`operator-job-row-${j.id}`}>
                          <td className="px-2 py-1 align-top">
                            {j.created_at || ""}
                          </td>
                          <td className="px-2 py-1 align-top">{j.title || "Untitled"}</td>
                          <td className="px-2 py-1 align-top">{j.city_id}</td>
                          <td className="px-2 py-1 align-top">{j.service_category_id}</td>
                          <td className="px-2 py-1 align-top">{j.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      </main>
      <Toaster />
    </div>
  );
}

function ContractorLoginPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { token, saveToken } = useAuth("contractor_jwt");
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (token) {
      navigate("/contractor/dashboard", { replace: true });
    }
  }, [token, navigate]);

  async function handleLogin({ email, password }) {
    setSubmitting(true);
    try {
      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", password);
      const res = await axios.post("/auth/login", formData, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      saveToken(res.data.access_token);
      navigate("/contractor/dashboard", { replace: true });
    } catch (err) {
      console.error("Contractor login failed", err);
      toast({ title: "Login failed", description: "Check your credentials and role." });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-title">Contractor login</div>
      </header>
      <main className="app-main">
        <section>
          <AuthForm
            title="Sign in as contractor"
            onSubmit={handleLogin}
            submitting={submitting}
            dataTestIdPrefix="contractor-login"
          />
        </section>
      </main>
      <Toaster />
    </div>
  );
}

function ContractorDashboard() {
  const { toast } = useToast();
  const { token } = useAuth("contractor_jwt");
  const navigate = useNavigate();
  const [tab, setTab] = React.useState("offers");
  const [offers, setOffers] = React.useState([]);
  const [jobs, setJobs] = React.useState([]);

  React.useEffect(() => {
    if (!token) {
      navigate("/contractor/login", { replace: true });
    }
  }, [token, navigate]);

  React.useEffect(() => {
    async function loadOffers() {
      try {
        const res = await axios.get("/contractors/me/offers", {
          headers: { Authorization: `Bearer ${token}` },
        });
        setOffers(res.data);
      } catch (err) {
        console.error("Failed to load offers", err);
      }
    }
    async function loadJobs() {
      try {
        const res = await axios.get("/contractors/me/jobs", {
          headers: { Authorization: `Bearer ${token}` },
        });
        setJobs(res.data);
      } catch (err) {
        console.error("Failed to load jobs", err);
      }
    }
    if (token) {
      loadOffers();
      loadJobs();
    }
  }, [token]);

  async function acceptJob(jobId) {
    try {
      await axios.post(
        `/contractors/offers/${jobId}/accept`,
        {},
        { headers: { Authorization: `Bearer ${token}` } },
      );
      toast({ title: "Job accepted", description: "You can now prepare a quote with the operator." });
      const [offersRes, jobsRes] = await Promise.all([
        axios.get("/contractors/me/offers", { headers: { Authorization: `Bearer ${token}` } }),
        axios.get("/contractors/me/jobs", { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      setOffers(offersRes.data);
      setJobs(jobsRes.data);
    } catch (err) {
      console.error("Accept job failed", err);
      toast({ title: "Unable to accept", description: "This job may have been taken already." });
    }
  }

  async function markCompleted(jobId) {
    try {
      await axios.post(
        `/contractors/jobs/${jobId}/mark-complete`,
        { completion_note: "Marked complete via dashboard" },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      toast({ title: "Job completed", description: "Payout will be queued by the operator." });
      const res = await axios.get("/contractors/me/jobs", { headers: { Authorization: `Bearer ${token}` } });
      setJobs(res.data);
    } catch (err) {
      console.error("Mark complete failed", err);
      toast({ title: "Unable to complete", description: "Ensure the job is confirmed first." });
    }
  }

  return (
    <div className="app-shell" data-testid="contractor-dashboard">
      <header className="app-header">
        <div>
          <div className="app-header-title">Contractor portal</div>
          <div className="app-tagline">Accept jobs, finish work, and see payouts queued.</div>
        </div>
      </header>
      <main className="app-main">
        <section className="space-y-3">
          <div className="flex gap-2" data-testid="contractor-tabs">
            <Button
              variant={tab === "offers" ? "default" : "outline"}
              onClick={() => setTab("offers")}
              data-testid="contractor-tab-offers"
            >
              Offers
            </Button>
            <Button
              variant={tab === "jobs" ? "default" : "outline"}
              onClick={() => setTab("jobs")}
              data-testid="contractor-tab-jobs"
            >
              My jobs
            </Button>
          </div>

          {tab === "offers" && (
            <Card data-testid="contractor-offers-card">
              <CardHeader>
                <CardTitle className="text-base">Available offers</CardTitle>
              </CardHeader>
              <CardContent>
                {offers.length === 0 ? (
                  <p className="text-sm text-slate-500" data-testid="contractor-offers-empty">
                    No matching offers right now.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {offers.map((j) => (
                      <div
                        key={j.id}
                        className="flex items-center justify-between rounded border border-slate-200 p-2 text-xs"
                        data-testid={`contractor-offer-${j.id}`}
                      >
                        <div>
                          <div className="font-medium">{j.title || "Untitled"}</div>
                          <div className="text-slate-500">{j.description?.slice(0, 80)}</div>
                        </div>
                        <Button
                          size="sm"
                          onClick={() => acceptJob(j.id)}
                          data-testid={`contractor-accept-${j.id}`}
                        >
                          Accept
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {tab === "jobs" && (
            <Card data-testid="contractor-jobs-card">
              <CardHeader>
                <CardTitle className="text-base">My jobs</CardTitle>
              </CardHeader>
              <CardContent>
                {jobs.length === 0 ? (
                  <p className="text-sm text-slate-500" data-testid="contractor-jobs-empty">
                    You haven&apos;t accepted any jobs yet.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {jobs.map((j) => (
                      <div
                        key={j.id}
                        className="flex items-center justify-between rounded border border-slate-200 p-2 text-xs"
                        data-testid={`contractor-job-${j.id}`}
                      >
                        <div>
                          <div className="font-medium">{j.title || "Untitled"}</div>
                          <div className="text-slate-500">Status: {j.status}</div>
                        </div>
                        {j.status === "confirmed" || j.status === "in_progress" ? (
                          <Button
                            size="sm"
                            onClick={() => markCompleted(j.id)}
                            data-testid={`contractor-complete-${j.id}`}
                          >
                            Mark completed
                          </Button>
                        ) : null}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </section>
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
        <Route path="/jobs/:jobId/status" element={<JobStatusPage />} />
        <Route path="/operator/login" element={<OperatorLoginPage />} />
        <Route path="/operator/dashboard" element={<OperatorDashboard />} />
        <Route path="/contractor/login" element={<ContractorLoginPage />} />
        <Route path="/contractor/dashboard" element={<ContractorDashboard />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
