import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../AuthContext";
import { AppHeader } from "../components/AppHeader";

export function ProfilePage() {
  const { me, refresh } = useAuth();
  const [fullName, setFullName] = useState(""); const [email, setEmail] = useState(""); const [tenantName, setTenantName] = useState("");
  const [currentPassword, setCurrentPassword] = useState(""); const [newPassword, setNewPassword] = useState(""); const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false); const [message, setMessage] = useState(""); const [error, setError] = useState("");

  useEffect(() => { if (me) { setFullName(me.user.full_name); setEmail(me.user.email); setTenantName(me.tenant_name); } }, [me]);

  async function saveIdentity(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(""); setMessage("");
    try { await api.updateProfile({ full_name: fullName, email, tenant_name: tenantName, current_password: currentPassword || undefined }); await refresh(); setCurrentPassword(""); setMessage("Profile updated."); }
    catch (err) { setError(err instanceof Error ? err.message : "Profile could not be updated"); } finally { setSaving(false); }
  }
  async function savePassword(event: FormEvent) {
    event.preventDefault(); setError(""); setMessage("");
    if (newPassword !== confirmPassword) { setError("New passwords do not match"); return; }
    setSaving(true);
    try { await api.updateProfile({ current_password: currentPassword, new_password: newPassword }); setCurrentPassword(""); setNewPassword(""); setConfirmPassword(""); setMessage("Password updated."); }
    catch (err) { setError(err instanceof Error ? err.message : "Password could not be updated"); } finally { setSaving(false); }
  }
  const initials = fullName.trim().split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase() || "U";
  return <div className="app-shell"><AppHeader /><main className="profile-page">
    <div className="profile-heading"><div className="profile-large-avatar">{initials}</div><div><h1>Profile settings</h1><p>Manage your account identity, workspace name, and password.</p></div></div>
    {error ? <p className="error">{error}</p> : null}{message ? <p className="success-banner">{message}</p> : null}
    <div className="profile-grid"><section className="box profile-card"><div><h2>Account details</h2><p>Changes appear across the platform immediately.</p></div><form className="stack" onSubmit={saveIdentity}>
      <label>Full name<input value={fullName} onChange={(event) => setFullName(event.target.value)} required /></label>
      <label>Email address<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /><small>Changing your email requires your current password.</small></label>
      <label>Tenant / workspace name<input value={tenantName} onChange={(event) => setTenantName(event.target.value)} required /><small>This is shared with everyone in your tenant.</small></label>
      {email.toLowerCase() !== me?.user.email.toLowerCase() ? <label>Current password<input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></label> : null}
      <div className="form-actions"><button className="btn btn-primary btn-large" disabled={saving}>Save profile</button></div>
    </form></section><section className="box profile-card"><div><h2>Change password</h2><p>Use at least eight characters.</p></div><form className="stack" onSubmit={savePassword}>
      <label>Current password<input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></label>
      <label>New password<input type="password" minLength={8} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required /></label>
      <label>Confirm new password<input type="password" minLength={8} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required /></label>
      <div className="form-actions"><button className="btn btn-primary btn-large" disabled={saving}>Update password</button></div>
    </form></section></div>
  </main></div>;
}
