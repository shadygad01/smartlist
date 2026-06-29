import { NextResponse } from 'next/server';
import { readFileSync } from 'fs';
import { join } from 'path';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export async function GET() {
  try {
    // SNAPSHOT_PATH env overrides default; default resolves to monorepo root
    const snapshotPath =
      process.env.SNAPSHOT_PATH ||
      join(process.cwd(), '..', 'presentation_snapshot.json');
    const raw = readFileSync(snapshotPath, 'utf-8');
    const data = JSON.parse(raw);
    return NextResponse.json(data, {
      headers: {
        'Cache-Control': 'no-store',
        'X-Snapshot-Source': snapshotPath,
      },
    });
  } catch {
    return NextResponse.json(
      { error: 'Snapshot unavailable — constitutional engine not yet run' },
      { status: 503 }
    );
  }
}
