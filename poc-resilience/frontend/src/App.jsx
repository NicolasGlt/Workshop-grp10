import { useCallback, useEffect, useState } from 'react'

// Toutes les requêtes passent par /api -> WAF -> nginx frontend -> Payment API
async function api(path, { token, ...opts } = {}) {
  const res = await fetch(`/api${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join(', ') : data.detail
    throw new Error(detail || `Erreur HTTP ${res.status}`)
  }
  return data
}

const eur = (v) => Number(v).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })
const DECLINE_FR = {
  insufficient_funds: 'Fonds insuffisants',
  card_blocked: 'Carte bloquée',
  card_not_found: 'Carte inconnue de la banque',
  invalid_amount: 'Montant invalide',
}

// ----- Formulaire de connexion réutilisable -----
function LoginForm({ onLogin, compact }) {
  const [email, setEmail] = useState('alice.martin@poc.local')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    try {
      const { access_token } = await api('/login', { method: 'POST', body: JSON.stringify({ email, password }) })
      onLogin(access_token)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form onSubmit={submit}>
      {!compact && <h2>Connexion</h2>}
      <label>Email<input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></label>
      <label>Mot de passe<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
      <button type="submit">Se connecter</button>
      {error && <p className="error">{error}</p>}
      <p className="hint">Démo : alice.martin / bob.durand / chloe.petit @poc.local — mot de passe Demo1234!</p>
    </form>
  )
}

// ================= PAGE DE CHECKOUT (type PayPal) =================
function Checkout({ paymentId }) {
  const [token, setToken] = useState(null)
  const [pay, setPay] = useState(null)
  const [cards, setCards] = useState([])
  const [cardId, setCardId] = useState('')
  const [result, setResult] = useState(null)   // { status, reason, return_url }
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api(`/payments/${paymentId}/public`).then(setPay).catch((e) => setError(e.message))
  }, [paymentId])

  useEffect(() => {
    if (!token) return
    api('/cards', { token }).then((cs) => { setCards(cs); setCardId(cs[0]?.id_card ?? '') }).catch((e) => setError(e.message))
  }, [token])

  const pay_now = async () => {
    setBusy(true); setError('')
    try {
      const r = await api(`/payments/${paymentId}/confirm`, {
        method: 'POST', token, body: JSON.stringify({ card_id: Number(cardId) }),
      })
      setResult(r)
      if (r.status === 'approved') setTimeout(() => { window.location.href = r.return_url }, 1800)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="checkout">
      <header><h1>Pay<span className="accent">Poc</span></h1><span className="badge">Paiement sécurisé</span></header>

      {error && <div className="card"><p className="error">{error}</p></div>}

      {pay && (
        <div className="card">
          <p className="muted">Paiement à</p>
          <h2 className="merchant">{pay.merchant_name}</h2>
          <p className="pay-amount">{eur(pay.amount)}</p>

          {pay.status !== 'created' ? (
            <p className="muted">Ce paiement a déjà été traité ({pay.status}).</p>
          ) : result ? (
            <div className={`result ${result.status}`}>
              {result.status === 'approved' ? (
                <><p className="ok big">Paiement approuvé ✓</p><p className="muted">Redirection vers la boutique…</p></>
              ) : (
                <>
                  <p className="error big">Paiement refusé</p>
                  <p className="muted">{DECLINE_FR[result.reason] || result.reason}</p>
                  <button onClick={() => setResult(null)}>Réessayer</button>
                  <a className="return-link" href={result.return_url}>Retour à la boutique</a>
                </>
              )}
            </div>
          ) : !token ? (
            <>
              <p className="muted">Connectez-vous à votre compte PayPoc pour payer.</p>
              <LoginForm onLogin={setToken} compact />
            </>
          ) : (
            <>
              <label>Carte
                <select value={cardId} onChange={(e) => setCardId(e.target.value)}>
                  {cards.map((c) => (
                    <option key={c.id_card} value={c.id_card}>
                      {c.brand.toUpperCase()} •••• {c.card_last4} — {c.cardholder_name}
                    </option>
                  ))}
                </select>
              </label>
              <button className="pay-btn" disabled={busy || !cardId} onClick={pay_now}>
                {busy ? 'Traitement…' : `Payer ${eur(pay.amount)}`}
              </button>
            </>
          )}
        </div>
      )}
      <p className="hint center">POC Resilience-Alpha — paiement fictif, aucune transaction réelle.</p>
    </main>
  )
}

// ================= PORTEFEUILLE (cartes + historique) =================
function Wallet({ token, onLogout }) {
  const [cards, setCards] = useState([])
  const [payments, setPayments] = useState([])
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [cs, ps] = await Promise.all([api('/cards', { token }), api('/payments/mine', { token })])
      setCards(cs); setPayments(ps)
    } catch (e) {
      if (e.message.includes('Token')) onLogout()
      setError(e.message)
    }
  }, [token, onLogout])

  useEffect(() => { refresh() }, [refresh])

  return (
    <>
      <section className="card">
        <div className="row-between"><h2>Mes cartes</h2><button className="ghost" onClick={onLogout}>Déconnexion</button></div>
        <table>
          <thead><tr><th>Carte</th><th>Titulaire</th><th>Expiration</th><th className="num">Solde</th></tr></thead>
          <tbody>
            {cards.map((c) => (
              <tr key={c.id_card}>
                <td className="mono">{c.brand.toUpperCase()} •••• {c.card_last4}{c.blocked && <span className="tag declined" style={{ marginLeft: 8 }}>bloquée</span>}</td>
                <td>{c.cardholder_name}</td>
                <td>{c.expiration_date}</td>
                <td className="num">{c.balance != null ? eur(c.balance) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2>Mes paiements</h2>
        {error && <p className="error">{error}</p>}
        <table>
          <thead><tr><th>Date</th><th>Marchand</th><th>Statut</th><th className="num">Montant</th></tr></thead>
          <tbody>
            {payments.map((p) => (
              <tr key={p.id_payment}>
                <td>{new Date(p.created_at).toLocaleString('fr-FR')}</td>
                <td>{p.merchant_name}</td>
                <td><span className={`tag ${p.status}`}>{p.status === 'approved' ? 'approuvé' : p.status === 'declined' ? 'refusé' : p.status}{p.decline_reason ? ` · ${DECLINE_FR[p.decline_reason] || p.decline_reason}` : ''}</span></td>
                <td className="num">{eur(p.amount)}</td>
              </tr>
            ))}
            {payments.length === 0 && <tr><td colSpan="4" className="muted">Aucun paiement pour l'instant.</td></tr>}
          </tbody>
        </table>
      </section>
    </>
  )
}

export default function App() {
  const params = new URLSearchParams(window.location.search)
  const paymentId = params.get('payment_id')
  const [token, setToken] = useState(null)

  if (paymentId) return <Checkout paymentId={paymentId} />

  return (
    <main>
      <header><h1>Pay<span className="accent">Poc</span></h1><span className="badge">Resilience-Alpha</span></header>
      {token ? <Wallet token={token} onLogout={() => setToken(null)} /> : <div className="card narrow"><LoginForm onLogin={setToken} /></div>}
    </main>
  )
}
