import React from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useNavigate,
  useSearchParams,
  useParams,
} from "react-router-dom";
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

// ------------------------
// Shared hooks & helpers
// ------------------------

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

// ------------------------
// Client: intake + status
// ------------------------

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
  const [otherDescription, setOtherDescription] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [statusLink, setStatusLink] = React.useState(null);

  const onChange = (field) => (e) => {
    const value = e?.target ? (e.target.type === "checkbox" ? e.target.checked : e.target.value) : e;
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const regularCategories = categories.filter((c) => c.slug !== "other");

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      let finalServiceSlug = form.service_category_slug;
      // For v1, map "Other" to the first listed category while appending details
      if (form.service_category_slug === "other") {
        finalServiceSlug = categories[0]?.slug || "";
      }

      let finalDescription = form.description;
      if (form.service_category_slug === "other" && otherDescription.trim()) {
        finalDescription = `${form.description}\n\nClient described an unlisted service: ${otherDescription.trim()}`;
      }

      const payload = {
        city_slug: form.city_slug,
        service_category_slug: finalServiceSlug,
        title: form.title || undefined,
        description: finalDescription,
        zip: form.zip,
        preferred_timing: form.preferred_timing,
        client_name: form.client_name,
        client_phone: form.client_phone,
        client_email: form.client_email || undefined,
        is_test: form.is_test,
      };
      const res = await axios.post("/jobs", payload);
      const { job_id, client_view_token } = res.data;
      const link = `/jobs/${job_id}/status?token=${encodeURIComponent(client_view_token)}`;
      setStatusLink(link);
      toast({
        title: "Thanks! We’ve received your request.",
        description: "We’ll be in touch shortly.",
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

  const selectedCityName =
    cities.find((c) => c.slug === form.city_slug)?.name || "your area";

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <div className="app-header-title">Request a service with ProBridge</div>
          <div className="app-tagline">Tell us about your project. We’re here to help!</div>
        </div>
      </header>

      <main className="app-main">
        <section>
          <div className="app-hero-title" data-testid="hero-main-title">
            ProBridge connects you with trusted local pros.
          </div>
          <p className="app-hero-subtitle" data-testid="hero-subtitle">
            Share a few details and we’ll route your request to a vetted contractor.
          </p>
          <div className="app-hero-chip-row">
            <span className="app-hero-chip" data-testid="chip-city">Starting in Albuquerque</span>
            <span className="app-hero-chip" data-testid="chip-handyman">Home services first</span>
            <span className="app-hero-chip" data-testid="chip-operator">Operator-managed quotes & routing</span>
          </div>

          <div className="app-secondary-surface" data-testid="info-sandbox">
            <strong>Test request.</strong> You can mark this as a test at the bottom of the form if you’re just trying things out.
          </div>
        </section>

        <section>
          <div className="app-panel" data-testid="client-job-request-panel">
            <div className="app-panel-header">
              <div>
                <div className="app-panel-title">Service details</div>
                <div className="app-panel-subtitle">We’ll use this to match you to the right pro.</div>
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-3" data-testid="job-request-form">
              <div className="app-input-row">
                <div>
                  <label className="text-xs text-slate-600" htmlFor="city" data-testid="label-city">
                    Select your city
                  </label>
                  <Select
                    onValueChange={(v) => onChange("city_slug")({ target: { value: v } })}
                    value={form.city_slug}
                  >
                    <SelectTrigger id="city" data-testid="input-city">
                      <SelectValue placeholder={loading ? "Loading cities…" : "Choose your city…"} />
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
                  <label className="text-xs text-slate-600" htmlFor="category" data-testid="label-category">
                    What kind of help do you need?
                  </label>
                  <Select
                    onValueChange={(v) => onChange("service_category_slug")({ target: { value: v } })}
                    value={form.service_category_slug}
                  >
                    <SelectTrigger id="category" data-testid="input-category">
                      <SelectValue placeholder={loading ? "Loading services…" : "Pick a service…"} />
                    </SelectTrigger>
                    <SelectContent>
                      {regularCategories.map((s) => (
                        <SelectItem key={s.id} value={s.slug} data-testid={`input-category-option-${s.slug}`}>
                          {s.display_name}
                        </SelectItem>
                      ))}
                      <SelectItem value="other" data-testid="input-category-option-other">
                        Other (describe below)
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {form.service_category_slug === "other" && (
                <div>
                  <label className="text-xs text-slate-600" htmlFor="other-desc" data-testid="label-other-description">
                    Describe your request
                  </label>
                  <Textarea
                    id="other-desc"
                    rows={3}
                    placeholder="Share what you need if it’s not listed above."
                    value={otherDescription}
                    onChange={(e) => setOtherDescription(e.target.value)}
                    data-testid="input-other-description"
                  />
                </div>
              )}

              <div>
                <label className="text-xs text-slate-600" htmlFor="title" data-testid="label-title">
                  Give your request a title (optional)
                </label>
                <Input
                  id="title"
                  data-testid="input-title"
                  placeholder="e.g., Mount a TV"
                  value={form.title}
                  onChange={onChange("title")}
                />
              </div>

              <div>
                <label className="text-xs text-slate-600" htmlFor="description" data-testid="label-description">
                  Describe the job
                </label>
                <Textarea
                  id="description"
                  data-testid="input-description"
                  placeholder="Provide any details our pros should know…"
                  rows={4}
                  value={form.description}
                  onChange={onChange("description")}
                />
              </div>

              <div className="app-input-row">
                <div>
                  <label className="text-xs text-slate-600" htmlFor="zip" data-testid="label-zip">
                    Where are you located?
                  </label>
                  <Input
                    id="zip"
                    data-testid="input-zip"
                    placeholder="ZIP code or full address…"
                    value={form.zip}
                    onChange={onChange("zip")}
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-600" htmlFor="timing" data-testid="label-preferred-timing">
                    Preferred timing
                  </label>
                  <Select
                    onValueChange={(v) => onChange("preferred_timing")({ target: { value: v } })}
                    value={form.preferred_timing}
                  >
                    <SelectTrigger id="timing" data-testid="input-preferred-timing">
                      <SelectValue placeholder="Pick a date or time range…" />
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

              <div className="app-divider-label">Contact information</div>
              <div className="app-input-row">
                <div>
                  <label className="text-xs text-slate-600" htmlFor="client_name" data-testid="label-client-name">
                    Your name
                  </label>
                  <Input
                    id="client_name"
                    data-testid="input-client-name"
                    value={form.client_name}
                    onChange={onChange("client_name")}
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-600" htmlFor="client_phone" data-testid="label-client-phone">
                    Phone number
                  </label>
                  <Input
                    id="client_phone"
                    data-testid="input-client-phone"
                    placeholder="We’ll send updates and a quote here."
                    value={form.client_phone}
                    onChange={onChange("client_phone")}
                  />
                </div>
              </div>

              <div>
                <label className="text-xs text-slate-600" htmlFor="client_email" data-testid="label-client-email">
                  Email address
                </label>
                <Input
                  id="client_email"
                  data-testid="input-client-email"
                  type="email"
                  value={form.client_email}
                  onChange={onChange("client_email")}
                />
                <p className="mt-1 text-[11px] text-slate-500" data-testid="contact-subtext">
                  We’ll send updates and a quote here.
                </p>
              </div>

              <div className="flex items-center justify-between gap-3 pt-1">
                <label className="flex items-center gap-2 text-xs text-slate-600" data-testid="label-is-test">
                  <input
                    type="checkbox"
                    checked={form.is_test}
                    onChange={onChange("is_test")}
                    className="h-3.5 w-3.5 rounded border-slate-300 bg-white"
                    data-testid="input-is-test-toggle"
                  />
                  <span>Test request</span>
                </label>
                <span className="text-[11px] text-slate-500" data-testid="sandbox-tooltip">
                  Check this if you’re just trying out the system.
                </span>
              </div>

              <div className="flex items-center justify-between pt-3">
                <Button
                  type="submit"
                  disabled={submitting}
                  data-testid="job-request-submit-button"
                >
                  {submitting ? "Submitting…" : "Submit my request"}
                </Button>

                {statusLink && (
                  <a
                    href={statusLink}
                    className="text-xs text-indigo-600 hover:underline"
                    data-testid="job-status-link"
                  >
                    Open status page
                  </a>
                )}
              </div>
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

  const isMatching = job && (job.status === "new" || job.status === "offering_contractors");
  const hasQuoteReady = job && job.quote_status === "sent_to_client" && job.status === "quote_sent";
  const isPaidOrConfirmed = job && (job.payment_status === "succeeded" || job.status === "confirmed");

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <div className="app-header-title">Your ProBridge job</div>
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
                    <div className="text-xs text-slate-500">Your ProBridge job</div>
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

                  {isMatching && (
                    <p className="text-xs text-slate-600" data-testid="job-status-matching-copy">
                      We’re matching your request with a trusted local pro…
                    </p>
                  )}

                  {job.quote_total_cents != null && (
                    <div className="border-t border-slate-200 pt-3 mt-2">
                      <div className="text-xs text-slate-500">Your ProBridge quote</div>
                      <div className="text-lg font-semibold" data-testid="job-quote-total">
                        ${(job.quote_total_cents / 100).toFixed(2)} USD
                      </div>
                    </div>
                  )}

                  {hasQuoteReady && (
                    <div className="pt-2" data-testid="job-quote-ready-section">
                      <p className="text-xs text-slate-600 mb-1">Your pro has sent a quote.</p>
                      <Button
                        onClick={handleApproveAndPay}
                        disabled={approving}
                        data-testid="approve-and-pay-button"
                      >
                        {approving ? "Opening checkout…" : "Approve quote"}
                      </Button>
                      <p className="mt-1 text-[11px] text-slate-500" data-testid="approve-quote-tooltip">
                        Approve to proceed to payment. We’ll hold the payment securely until the job is complete.
                      </p>
                    </div>
                  )}

                  {isPaidOrConfirmed && (
                    <p className="text-xs text-emerald-700" data-testid="payment-confirmation-text">
                      Thank you! We’ve received your payment. Your job is confirmed.
                    </p>
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

// ------------------------
// Auth helpers
// ------------------------

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
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

// ------------------------
// Operator portal
// ------------------------

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
        <div className="app-header-title">Operator Login</div>
      </header>
      <main className="app-main">
        <section>
          <AuthForm
            title="Operator Login"
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
  const [selectedJobId, setSelectedJobId] = React.useState(null);
  const [quoteForm, setQuoteForm] = React.useState({ label: "Base visit", type: "base", quantity: 1, unit_price_cents: "" });
  const [contractorTab, setContractorTab] = React.useState("jobs");
  const [contractors, setContractors] = React.useState([]);
  const [updateStatus, setUpdateStatus] = React.useState("");
  const { cities, categories } = useCitiesAndCategories();

  React.useEffect(() => {
    if (!token) {
      navigate("/operator/login", { replace: true });
    }
  }, [token, navigate]);

  React.useEffect(() => {
    async function loadJobs() {
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
    if (token) loadJobs();
  }, [filters, token, toast]);

  React.useEffect(() => {
    async function loadContractors() {
      try {
        const res = await axios.get("/operator/contractors", {
          headers: { Authorization: `Bearer ${token}` },
        });
        setContractors(res.data);
      } catch (err) {
        console.error("Failed to load contractors", err);
      }
    }
    if (token && contractorTab === "contractors") {
      loadContractors();
    }
  }, [token, contractorTab]);

  const selectedJob = jobs.find((j) => j.id === selectedJobId) || null;

  async function handleCreateQuote(e) {
    e.preventDefault();
    if (!selectedJobId) return;
    try {
      const body = {
        line_items: [
          {
            type: quoteForm.type,
            label: quoteForm.label,
            quantity: Number(quoteForm.quantity) || 1,
            unit_price_cents: Number(quoteForm.unit_price_cents) || 0,
          },
        ],
      };
      await axios.post(`/operator/jobs/${selectedJobId}/quotes`, body, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast({ title: "Quote drafted", description: "You can now send it to the client." });
    } catch (err) {
      console.error("Create quote failed", err);
      toast({ title: "Unable to create quote", description: "Check fields and try again." });
    }
  }

  async function handleSendQuote() {
    if (!selectedJobId) return;
    try {
      await axios.post(`/operator/jobs/${selectedJobId}/send-quote`, {}, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast({ title: "Quote sent", description: "The client will see it on their status page." });
    } catch (err) {
      console.error("Send quote failed", err);
      toast({ title: "Unable to send quote", description: "Ensure a draft exists first." });
    }
  }

  async function handleUpdateStatus() {
    if (!selectedJobId || !updateStatus) return;
    try {
      await axios.patch(
        `/operator/jobs/${selectedJobId}`,
        { status: updateStatus },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      toast({ title: "Status updated", description: "Job status has been updated." });
      // Refresh jobs
      const res = await axios.get("/operator/jobs", {
        params: filters,
        headers: { Authorization: `Bearer ${token}` },
      });
      setJobs(res.data);
    } catch (err) {
      console.error("Update status failed", err);
      toast({ title: "Unable to update status", description: "Please try again." });
    }
  }

  return (
    <div className="app-shell" data-testid="operator-dashboard">
      <header className="app-header">
        <div>
          <div className="app-header-title">ProBridge Operator Dashboard</div>
        </div>
      </header>
      <main className="app-main">
        <section className="space-y-3">
          <div className="flex flex-wrap gap-4 items-end" data-testid="operator-filters">
            <div>
              <div className="text-[11px] text-slate-500 mb-1">City</div>
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
            </div>

            <div>
              <div className="text-[11px] text-slate-500 mb-1">Service</div>
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
            </div>

            <div>
              <div className="text-[11px] text-slate-500 mb-1">Status</div>
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

            <div className="flex gap-1 ml-auto" data-testid="operator-main-tabs">
              <Button
                variant={contractorTab === "jobs" ? "default" : "outline"}
                size="sm"
                onClick={() => setContractorTab("jobs")}
                data-testid="operator-tab-jobs"
              >
                Jobs
              </Button>
              <Button
                variant={contractorTab === "contractors" ? "default" : "outline"}
                size="sm"
                onClick={() => setContractorTab("contractors")}
                data-testid="operator-tab-contractors"
              >
                Contractors
              </Button>
            </div>
          </div>

          {contractorTab === "jobs" && (
            <Card data-testid="operator-jobs-card">
              <CardHeader>
                <CardTitle className="text-base">All Jobs</CardTitle>
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
                          <th className="px-2 py-1 text-left">Title</th>
                          <th className="px-2 py-1 text-left">Status</th>
                          <th className="px-2 py-1 text-left">ZIP</th>
                        </tr>
                      </thead>
                      <tbody>
                        {jobs.map((j) => (
                          <tr
                            key={j.id}
                            className="border-b border-slate-100 cursor-pointer hover:bg-slate-50"
                            data-testid={`operator-job-row-${j.id}`}
                            onClick={() => setSelectedJobId(j.id)}
                          >
                            <td className="px-2 py-1 align-top">{j.title || "Untitled"}</td>
                            <td className="px-2 py-1 align-top">{j.status}</td>
                            <td className="px-2 py-1 align-top">{j.zip}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {contractorTab === "contractors" && (
            <Card data-testid="operator-contractors-card">
              <CardHeader>
                <CardTitle className="text-base">Contractors</CardTitle>
              </CardHeader>
              <CardContent>
                {contractors.length === 0 ? (
                  <p className="text-sm text-slate-500" data-testid="operator-contractors-empty">
                    No contractors yet.
                  </p>
                ) : (
                  <div className="space-y-2" data-testid="operator-contractors-list">
                    {contractors.map((c) => (
                      <div
                        key={c.id}
                        className="flex items-center justify-between rounded border border-slate-200 p-2 text-xs"
                        data-testid={`operator-contractor-${c.id}`}
                      >
                        <div>
                          <div className="font-medium">{c.public_name}</div>
                          <div className="text-slate-500">{c.city}</div>
                          <div className="text-slate-500">
                            Services: {c.service_labels?.join(", ") || "—"}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-slate-500">Completed Jobs: {c.completed_jobs_count}</div>
                          <div className="text-slate-700 font-semibold">
                            ${(c.total_earnings_cents / 100).toFixed(2)} USD
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </section>

        {contractorTab === "jobs" && (
          <section>
            <Card data-testid="operator-job-detail-card">
              <CardHeader>
                <CardTitle className="text-base">Job detail & quote</CardTitle>
              </CardHeader>
              <CardContent>
                {!selectedJob && (
                  <p className="text-sm text-slate-500" data-testid="operator-job-detail-empty">
                    Select a job from the table to prepare a quote.
                  </p>
                )}
                {selectedJob && (
                  <div className="space-y-3" data-testid="operator-selected-job-panel">
                    <div>
                      <div className="text-xs text-slate-500">Title</div>
                      <div className="text-sm font-medium">{selectedJob.title || "Untitled"}</div>
                      <p className="mt-1 text-xs text-slate-500">{selectedJob.description}</p>
                    </div>
                    <form className="space-y-2" onSubmit={handleCreateQuote} data-testid="operator-quote-form">
                      <div>
                        <label className="text-xs text-slate-600" htmlFor="quote-label" data-testid="operator-quote-label">
                          Line item label
                        </label>
                        <Input
                          id="quote-label"
                          value={quoteForm.label}
                          onChange={(e) => setQuoteForm((f) => ({ ...f, label: e.target.value }))}
                          data-testid="operator-quote-label-input"
                        />
                      </div>
                      <div className="app-input-row">
                        <div>
                          <label className="text-xs text-slate-600" htmlFor="quote-qty" data-testid="operator-quote-quantity-label">
                            Quantity
                          </label>
                          <Input
                            id="quote-qty"
                            type="number"
                            value={quoteForm.quantity}
                            onChange={(e) => setQuoteForm((f) => ({ ...f, quantity: e.target.value }))}
                            data-testid="operator-quote-quantity-input"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-slate-600" htmlFor="quote-unit" data-testid="operator-quote-unit-price-label">
                            Unit price (cents)
                          </label>
                          <Input
                            id="quote-unit"
                            type="number"
                            value={quoteForm.unit_price_cents}
                            onChange={(e) => setQuoteForm((f) => ({ ...f, unit_price_cents: e.target.value }))}
                            data-testid="operator-quote-unit-price-input"
                          />
                        </div>
                      </div>
                      <Button type="submit" size="sm" data-testid="operator-quote-create-button">
                        Create draft quote
                      </Button>
                    </form>
                    <div className="flex flex-wrap gap-2 pt-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleSendQuote}
                        data-testid="operator-quote-send-button"
                      >
                        Send Quote
                      </Button>
                      <div className="flex items-end gap-2">
                        <div>
                          <label className="text-[11px] text-slate-500" htmlFor="update-status-select" data-testid="operator-update-status-label">
                            Update Status
                          </label>
                          <Select
                            value={updateStatus}
                            onValueChange={setUpdateStatus}
                          >
                            <SelectTrigger
                              id="update-status-select"
                              className="w-40"
                              data-testid="operator-update-status-select"
                            >
                              <SelectValue placeholder="Choose status" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="confirmed">Confirmed</SelectItem>
                              <SelectItem value="in_progress">In progress</SelectItem>
                              <SelectItem value="completed">Completed</SelectItem>
                              <SelectItem value="cancelled_by_client">Cancelled by client</SelectItem>
                              <SelectItem value="cancelled_internal">Cancelled internal</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handleUpdateStatus}
                          data-testid="operator-update-status-button"
                        >
                          Update Status
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </section>
        )}
      </main>
      <Toaster />
    </div>
  );
}

// ------------------------
// Contractor portal
// ------------------------

function ContractorWelcomePage() {
  // Join ProBridge landing screen for contractors
  const navigate = useNavigate();
  return (
    <div className="app-shell" data-testid="contractor-welcome-page">
      <header className="app-header">
        <div className="app-header-title">Join ProBridge</div>
      </header>
      <main className="app-main">
        <section>
          <Card data-testid="contractor-welcome-card">
            <CardHeader>
              <CardTitle className="text-base">Earn on your schedule. We connect you with local customers.</CardTitle>
            </CardHeader>
            <CardContent>
              <Button
                onClick={() => navigate("/contractor/signup")}
                data-testid="contractor-welcome-signup-button"
              >
                Sign up as a contractor
              </Button>
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
        <div className="app-header-title">Contractor Login</div>
        <a
          href="/contractor/signup"
          className="text-xs text-indigo-600 hover:underline"
          data-testid="contractor-login-signup-link"
        >
          Need an account? Sign up
        </a>
      </header>
      <main className="app-main">
        <section>
          <AuthForm
            title="Contractor Login"
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

function ContractorSignupPage() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const { cities, categories } = useCitiesAndCategories();
  const [form, setForm] = React.useState({
    name: "",
    email: "",
    phone: "",
    password: "",
    confirmPassword: "",
    city_slug: "",
    base_zip: "",
    radius_miles: "10",
    experience: "",
    availability: "",
    payout_method: "",
    referral_code: "",
    legal_name: "",
    suggest_city_name_text: "",
    suggest_zip: "",
    suggest_service_category_id: "",
  });
  const [selectedServices, setSelectedServices] = React.useState([]);
  const [submitting, setSubmitting] = React.useState(false);

  function updateField(field) {
    return (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));
  }

  function toggleService(id) {
    setSelectedServices((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (form.password !== form.confirmPassword) {
      toast({ title: "Passwords don&apos;t match", description: "Please re-enter them." });
      return;
    }
    if (!form.city_slug || selectedServices.length === 0) {
      toast({ title: "Missing fields", description: "City and at least one service are required." });
      return;
    }
    setSubmitting(true);
    try {
      const body = {
        name: form.name,
        email: form.email,
        phone: form.phone,
        password: form.password,
        city_slug: form.city_slug,
        base_zip: form.base_zip,
        radius_miles: Number(form.radius_miles) || 0,
        service_category_ids: selectedServices,
        bio: form.experience || undefined,
        suggest_city_name_text: form.suggest_city_name_text || undefined,
        suggest_zip: form.suggest_zip || undefined,
        suggest_service_category_id: form.suggest_service_category_id || undefined,
        // Additional profile fields like legal name, payout method, availability, and referral code
        // are captured in the UI for now and can be wired to the backend in a later iteration.
      };
      await axios.post("/contractors/signup", body);
      toast({ title: "Profile created", description: "You can log in to see available jobs." });
      navigate("/contractor/login", { replace: true });
    } catch (err) {
      console.error("Contractor signup failed", err);
      toast({ title: "Signup failed", description: "Check your details and try again." });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-title">Join ProBridge</div>
      </header>
      <main className="app-main">
        <section>
          <Card className="w-full max-w-xl" data-testid="contractor-signup-card">
            <CardHeader>
              <CardTitle className="text-base">Create your contractor profile</CardTitle>
            </CardHeader>
            <CardContent>
              <form
                onSubmit={handleSubmit}
                className="space-y-3"
                data-testid="contractor-signup-form"
              >
                <div className="app-input-row">
                  <div>
                    <label className="text-xs text-slate-600" htmlFor="signup-name" data-testid="contractor-signup-name-label">
                      Business or display name
                    </label>
                    <Input
                      id="signup-name"
                      value={form.name}
                      onChange={updateField("name")}
                      data-testid="contractor-signup-name-input"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-600" htmlFor="signup-legal" data-testid="contractor-signup-legal-label">
                      Legal name (for payments)
                    </label>
                    <Input
                      id="signup-legal"
                      value={form.legal_name}
                      onChange={updateField("legal_name")}
                      data-testid="contractor-signup-legal-input"
                    />
                  </div>
                </div>
                <div className="app-input-row">
                  <div>
                    <label className="text-xs text-slate-600" htmlFor="signup-email" data-testid="contractor-signup-email-label">
                      Email address
                    </label>
                    <Input
                      id="signup-email"
                      type="email"
                      value={form.email}
                      onChange={updateField("email")}
                      data-testid="contractor-signup-email-input"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-600" htmlFor="signup-phone" data-testid="contractor-signup-phone-label">
                      Phone number
                    </label>
                    <Input
                      id="signup-phone"
                      value={form.phone}
                      onChange={updateField("phone")}
                      data-testid="contractor-signup-phone-input"
                    />
                  </div>
                </div>
                <div className="app-input-row">
                  <div>
                    <label className="text-xs text-slate-600" htmlFor="signup-city" data-testid="contractor-signup-city-label">
                      City
                    </label>
                    <Select
                      value={form.city_slug}
                      onValueChange={(v) => setForm((prev) => ({ ...prev, city_slug: v }))}
                    >
                      <SelectTrigger id="signup-city" data-testid="contractor-signup-city-input">
                        <SelectValue placeholder="Select city" />
                      </SelectTrigger>
                      <SelectContent>
                        {cities.map((c) => (
                          <SelectItem key={c.id} value={c.slug} data-testid={`contractor-signup-city-${c.slug}`}>
                            {c.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label className="text-xs text-slate-600" htmlFor="signup-zip" data-testid="contractor-signup-zip-label">
                      Base ZIP
                    </label>
                    <Input
                      id="signup-zip"
                      value={form.base_zip}
                      onChange={updateField("base_zip")}
                      data-testid="contractor-signup-zip-input"
                    />
                  </div>
                </div>
                <div className="app-input-row">
                  <div>
                    <label className="text-xs text-slate-600" htmlFor="signup-radius" data-testid="contractor-signup-radius-label">
                      Radius (miles)
                    </label>
                    <Input
                      id="signup-radius"
                      type="number"
                      value={form.radius_miles}
                      onChange={updateField("radius_miles")}
                      data-testid="contractor-signup-radius-input"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-600" htmlFor="signup-payout" data-testid="contractor-signup-payout-label">
                      How would you like to get paid?
                    </label>
                    <Input
                      id="signup-payout"
                      placeholder="e.g., Zelle or Check"
                      value={form.payout_method}
                      onChange={updateField("payout_method")}
                      data-testid="contractor-signup-payout-input"
                    />
                  </div>
                </div>
                <div>
                  <label className="text-xs text-slate-600" data-testid="contractor-signup-services-label">
                    What kind of jobs do you take?
                  </label>
                  <div className="mt-1 flex flex-wrap gap-2" data-testid="contractor-signup-services-group">
                    {categories.map((s) => (
                      <label
                        key={s.id}
                        className="flex items-center gap-1 rounded border border-slate-200 px-2 py-1 text-xs"
                        data-testid={`contractor-signup-service-${s.slug}`}
                      >
                        <input
                          type="checkbox"
                          checked={selectedServices.includes(s.id)}
                          onChange={() => toggleService(s.id)}
                        />
                        <span>{s.display_name}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="text-xs text-slate-600" htmlFor="signup-experience" data-testid="contractor-signup-experience-label">
                    Reliability & Experience
                  </label>
                  <Textarea
                    id="signup-experience"
                    rows={3}
                    value={form.experience}
                    onChange={updateField("experience")}
                    data-testid="contractor-signup-experience-input"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-600" htmlFor="signup-availability" data-testid="contractor-signup-availability-label">
                    When are you available?
                  </label>
                  <Textarea
                    id="signup-availability"
                    rows={2}
                    placeholder="e.g., Weekdays 9–5, Saturdays 10–2"
                    value={form.availability}
                    onChange={updateField("availability")}
                    data-testid="contractor-signup-availability-input"
                  />
                </div>
                <div className="app-input-row">
                  <div>
                    <label className="text-xs text-slate-600" htmlFor="signup-password" data-testid="contractor-signup-password-label">
                      Password
                    </label>
                    <Input
                      id="signup-password"
                      type="password"
                      value={form.password}
                      onChange={updateField("password")}
                      data-testid="contractor-signup-password-input"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-600" htmlFor="signup-confirm" data-testid="contractor-signup-confirm-label">
                      Confirm password
                    </label>
                    <Input
                      id="signup-confirm"
                      type="password"
                      value={form.confirmPassword}
                      onChange={updateField("confirmPassword")}
                      data-testid="contractor-signup-confirm-input"
                    />
                  </div>
                </div>
                <div className="app-input-row">
                  <div>
                    <label className="text-xs text-slate-600" htmlFor="signup-referral" data-testid="contractor-signup-referral-label">
                      Referral Code (optional)
                    </label>
                    <Input
                      id="signup-referral"
                      value={form.referral_code}
                      onChange={updateField("referral_code")}
                      data-testid="contractor-signup-referral-input"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-600" data-testid="contractor-signup-suggest-label">
                      Suggest a new area (optional)
                    </label>
                    <div className="app-input-row mt-1">
                      <Input
                        placeholder="City or neighborhood"
                        value={form.suggest_city_name_text}
                        onChange={updateField("suggest_city_name_text")}
                        data-testid="contractor-signup-suggest-city-input"
                      />
                      <Input
                        placeholder="ZIP"
                        value={form.suggest_zip}
                        onChange={updateField("suggest_zip")}
                        data-testid="contractor-signup-suggest-zip-input"
                      />
                    </div>
                  </div>
                </div>
                <Button
                  type="submit"
                  disabled={submitting}
                  data-testid="contractor-signup-submit-button"
                >
                  {submitting ? "Creating profile…" : "Create my profile"}
                </Button>
              </form>
            </CardContent>
          </Card>
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
  const [acceptingId, setAcceptingId] = React.useState(null);
  const [savingJobId, setSavingJobId] = React.useState(null);
  const [completionNote, setCompletionNote] = React.useState("");

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
      setAcceptingId(jobId);
      await axios.post(
        `/contractors/offers/${jobId}/accept`,
        {},
        { headers: { Authorization: `Bearer ${token}` } },
      );
      toast({ title: "Job accepted", description: "You can now work with the operator on a quote." });
      const [offersRes, jobsRes] = await Promise.all([
        axios.get("/contractors/me/offers", { headers: { Authorization: `Bearer ${token}` } }),
        axios.get("/contractors/me/jobs", { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      setOffers(offersRes.data);
      setJobs(jobsRes.data);
    } catch (err) {
      console.error("Accept job failed", err);
      toast({ title: "Unable to accept", description: "This job may have been taken already." });
    } finally {
      setAcceptingId(null);
    }
  }

  async function markCompleted(jobId) {
    try {
      setSavingJobId(jobId);
      await axios.post(
        `/contractors/jobs/${jobId}/mark-complete`,
        { completion_note: completionNote || undefined },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      toast({ title: "Marked as completed.", description: "Thank you!" });
      const res = await axios.get("/contractors/me/jobs", { headers: { Authorization: `Bearer ${token}` } });
      setJobs(res.data);
      setCompletionNote("");
    } catch (err) {
      console.error("Mark complete failed", err);
      toast({ title: "Unable to complete", description: "Ensure the job is confirmed first." });
    } finally {
      setSavingJobId(null);
    }
  }

  return (
    <div className="app-shell" data-testid="contractor-dashboard">
      <header className="app-header">
        <div>
          <div className="app-header-title">Join ProBridge</div>
          <div className="app-tagline">Earn on your schedule. We connect you with local customers.</div>
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
              Available Jobs
            </Button>
            <Button
              variant={tab === "jobs" ? "default" : "outline"}
              onClick={() => setTab("jobs")}
              data-testid="contractor-tab-jobs"
            >
              Your Jobs
            </Button>
          </div>

          {tab === "offers" && (
            <Card data-testid="contractor-offers-card">
              <CardHeader>
                <CardTitle className="text-base">Available Jobs</CardTitle>
                <p className="mt-1 text-xs text-slate-500">Browse open requests in your area.</p>
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
                          disabled={acceptingId === j.id}
                          data-testid={`contractor-accept-${j.id}`}
                        >
                          {acceptingId === j.id ? "Accepting…" : "Accept job"}
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
                <CardTitle className="text-base">Your Jobs</CardTitle>
                <p className="mt-1 text-xs text-slate-500">
                  Your active jobs. Complete the tasks and enter a note when done.
                </p>
              </CardHeader>
              <CardContent>
                <div className="mb-3">
                  <label className="text-xs text-slate-600" htmlFor="completion-note" data-testid="completion-note-label">
                    Completion note
                  </label>
                  <Textarea
                    id="completion-note"
                    rows={2}
                    value={completionNote}
                    onChange={(e) => setCompletionNote(e.target.value)}
                    data-testid="completion-note-input"
                  />
                </div>
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
                        {(j.status === "confirmed" || j.status === "in_progress") && (
                          <Button
                            size="sm"
                            onClick={() => markCompleted(j.id)}
                            disabled={savingJobId === j.id}
                            data-testid={`contractor-complete-${j.id}`}
                          >
                            {savingJobId === j.id ? "Saving…" : "Mark completed"}
                          </Button>
                        )}
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

// ------------------------
// App routes
// ------------------------

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ClientHomePage />} />
        <Route path="/jobs/:jobId/status" element={<JobStatusPage />} />
        <Route path="/operator/login" element={<OperatorLoginPage />} />
        <Route path="/operator/dashboard" element={<OperatorDashboard />} />
        <Route path="/contractor" element={<ContractorWelcomePage />} />
        <Route path="/contractor/login" element={<ContractorLoginPage />} />
        <Route path="/contractor/signup" element={<ContractorSignupPage />} />
        <Route path="/contractor/dashboard" element={<ContractorDashboard />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
