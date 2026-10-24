import Link from "next/link";

export default function NotFound() {
  return (
    <div style={{ maxWidth: 480, margin: "96px auto", padding: "0 16px", textAlign: "center" }}>
      <h1 style={{ fontSize: 24, margin: 0 }}>Annonce introuvable</h1>
      <p style={{ color: "var(--secondary-text-color)" }}>
        Elle a peut-être été supprimée de Griffon, ou le lien est incomplet.
      </p>
      <Link href="/" style={{ color: "var(--primary-color)" }}>
        Retour à la recherche
      </Link>
    </div>
  );
}
