import { Client } from "pg";

/**
 * Invitation tokens are only ever emailed — no API exposes them, which is the
 * right call for production but leaves the browser with no way to reach the
 * accept-invite page. These tests read the token straight out of Postgres.
 *
 * DATABASE_URL is what CI sets for the e2e job; the fallback is the dev
 * database in backend/app/core/config.py. The driver prefix is SQLAlchemy's,
 * so strip it before handing the URL to node-postgres.
 */
const URL = (
  process.env.DATABASE_URL ?? "postgresql+asyncpg://rental:rental@localhost:5433/rental"
).replace("+asyncpg", "");

export async function invitationToken(email: string): Promise<string> {
  const client = new Client({ connectionString: URL });
  await client.connect();
  try {
    const { rows } = await client.query<{ token: string }>(
      "SELECT token FROM invitations WHERE email = $1 ORDER BY created_at DESC LIMIT 1",
      [email],
    );
    if (rows.length === 0) throw new Error(`No invitation found for ${email}`);
    return rows[0].token;
  } finally {
    await client.end();
  }
}
