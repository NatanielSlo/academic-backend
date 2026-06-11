# Content Generation - Usage Example

## Quick Start

### 1. Run Database Migration

```bash
cd backend
python run_migration.py
```

This creates the new tables for content generation.

### 2. Test with Existing Transcript

```bash
python test_content_generation.py
```

This will:
- Load `transcript_output.json`
- Extract outline (Pass 1)
- Generate notes (Pass 2a)
- Generate quiz (Pass 2b)
- Verify coverage (Pass 3)

### 3. Check Output

All generated files are saved to `logs/content_generation/`:

```
logs/content_generation/
├── outline_test-lecture-001_20240115_103000.json
├── notes_test-lecture-001_20240115_103045.md
├── quiz_test-lecture-001_20240115_103130.json
└── coverage_test-lecture-001_20240115_103215.json
```

## Production Usage

### Via API

#### 1. Process a lecture first

```bash
curl -X POST http://localhost:8000/api/lectures \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://live.rbg.tum.de/w/eidi/20838",
    "course_name": "EIDI",
    "lecture_number": "5"
  }'
```

Response:
```json
{
  "lecture_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing"
}
```

#### 2. Wait for processing to complete

Poll status:
```bash
curl http://localhost:8000/api/lectures/550e8400-e29b-41d4-a716-446655440000/status
```

Wait for `"status": "completed"`

#### 3. Generate comprehensive materials

```bash
curl -X POST http://localhost:8000/api/content/lectures/550e8400-e29b-41d4-a716-446655440000/generate \
  -H "Content-Type: application/json" \
  -d '{"num_quiz_questions": 20}'
```

Response:
```json
{
  "lecture_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "not_started",
  "progress_percent": 0,
  "current_step": "Queued for processing"
}
```

#### 4. Poll generation status

```bash
curl http://localhost:8000/api/content/lectures/550e8400-e29b-41d4-a716-446655440000/generation-status
```

Poll every 5 seconds. Status progression:
- `not_started` (0%)
- `generating_outline` (10-30%)
- `generating_notes` (30-50%)
- `generating_quiz` (50-70%)
- `verifying` (70-90%)
- `completed` (100%)

#### 5. Retrieve generated materials

**Get outline:**
```bash
curl http://localhost:8000/api/content/lectures/550e8400-e29b-41d4-a716-446655440000/outline
```

**Get notes:**
```bash
curl http://localhost:8000/api/content/lectures/550e8400-e29b-41d4-a716-446655440000/notes > notes.md
```

**Get quiz:**
```bash
curl http://localhost:8000/api/content/lectures/550e8400-e29b-41d4-a716-446655440000/comprehensive-quiz
```

**Get coverage report:**
```bash
curl http://localhost:8000/api/content/lectures/550e8400-e29b-41d4-a716-446655440000/coverage-report
```

**Get everything at once:**
```bash
curl http://localhost:8000/api/content/lectures/550e8400-e29b-41d4-a716-446655440000/all-materials
```

## Frontend Integration Example

### React/TypeScript

```typescript
// types.ts
interface ContentGenerationRequest {
  num_quiz_questions: number;
}

interface GenerationStatus {
  lecture_id: string;
  status: 'not_started' | 'generating_outline' | 'generating_notes' | 
          'generating_quiz' | 'verifying' | 'completed' | 'failed';
  progress_percent: number;
  current_step?: string;
  error_message?: string;
}

interface Quiz {
  lecture_id: string;
  quiz_metadata: {
    total_questions: number;
    topics_covered: string[];
    difficulty_distribution: Record<string, number>;
  };
  questions: QuizQuestion[];
  generated_at: string;
}

// api.ts
async function generateMaterials(lectureId: string, numQuestions: number = 20) {
  const response = await fetch(
    `${API_BASE}/api/content/lectures/${lectureId}/generate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ num_quiz_questions: numQuestions })
    }
  );
  return response.json();
}

async function checkGenerationStatus(lectureId: string): Promise<GenerationStatus> {
  const response = await fetch(
    `${API_BASE}/api/content/lectures/${lectureId}/generation-status`
  );
  return response.json();
}

async function getNotes(lectureId: string) {
  const response = await fetch(
    `${API_BASE}/api/content/lectures/${lectureId}/notes`
  );
  return response.json();
}

// Component.tsx
function MaterialsGenerator({ lectureId }: { lectureId: string }) {
  const [status, setStatus] = useState<GenerationStatus | null>(null);
  const [polling, setPolling] = useState(false);

  async function handleGenerate() {
    // Start generation
    await generateMaterials(lectureId, 20);
    
    // Start polling
    setPolling(true);
    const interval = setInterval(async () => {
      const status = await checkGenerationStatus(lectureId);
      setStatus(status);
      
      if (status.status === 'completed' || status.status === 'failed') {
        clearInterval(interval);
        setPolling(false);
      }
    }, 5000); // Poll every 5 seconds
  }

  return (
    <div>
      <button onClick={handleGenerate} disabled={polling}>
        Generate Study Materials
      </button>
      
      {status && (
        <div>
          <progress value={status.progress_percent} max={100} />
          <p>{status.current_step}</p>
          
          {status.status === 'completed' && (
            <div>
              <a href={`/lectures/${lectureId}/notes`}>View Notes</a>
              <a href={`/lectures/${lectureId}/quiz`}>Take Quiz</a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

## Python Script Integration

```python
import requests
import time
from typing import Optional

API_BASE = "http://localhost:8000"

def generate_and_wait(lecture_id: str, num_questions: int = 20) -> dict:
    """Generate materials and wait for completion."""
    
    # Start generation
    print(f"Starting generation for lecture {lecture_id}...")
    response = requests.post(
        f"{API_BASE}/api/content/lectures/{lecture_id}/generate",
        json={"num_quiz_questions": num_questions}
    )
    response.raise_for_status()
    
    # Poll status
    while True:
        status_response = requests.get(
            f"{API_BASE}/api/content/lectures/{lecture_id}/generation-status"
        )
        status = status_response.json()
        
        print(f"Status: {status['status']} ({status['progress_percent']}%) - {status.get('current_step', '')}")
        
        if status['status'] == 'completed':
            print("Generation complete!")
            break
        elif status['status'] == 'failed':
            raise Exception(f"Generation failed: {status.get('error_message')}")
        
        time.sleep(5)
    
    # Fetch all materials
    print("Fetching materials...")
    materials = requests.get(
        f"{API_BASE}/api/content/lectures/{lecture_id}/all-materials"
    ).json()
    
    return materials

# Usage
if __name__ == "__main__":
    lecture_id = "550e8400-e29b-41d4-a716-446655440000"
    materials = generate_and_wait(lecture_id, num_questions=15)
    
    # Save notes
    with open(f"notes_{lecture_id}.md", "w", encoding="utf-8") as f:
        f.write(materials["notes_markdown"])
    
    # Save quiz
    with open(f"quiz_{lecture_id}.json", "w", encoding="utf-8") as f:
        import json
        json.dump(materials["quiz"], f, indent=2)
    
    print(f"Coverage: {materials['coverage_report']['overall_assessment']['coverage_percent']}%")
    print(f"Quality: {materials['coverage_report']['overall_assessment']['quality_score']}")
```

## Common Workflows

### Workflow 1: Full Course Processing

```bash
# Process all lectures in a course
COURSE="EIDI"
LECTURES=(
  "https://live.rbg.tum.de/w/eidi/20838"
  "https://live.rbg.tum.de/w/eidi/20839"
  # ... more lectures
)

for i in "${!LECTURES[@]}"; do
  URL="${LECTURES[$i]}"
  NUM=$((i + 1))
  
  echo "Processing lecture $NUM..."
  
  # 1. Process lecture
  LECTURE_ID=$(curl -X POST http://localhost:8000/api/lectures \
    -H "Content-Type: application/json" \
    -d "{\"url\":\"$URL\",\"course_name\":\"$COURSE\",\"lecture_number\":\"$NUM\"}" \
    | jq -r '.lecture_id')
  
  # 2. Wait for processing
  while true; do
    STATUS=$(curl -s http://localhost:8000/api/lectures/$LECTURE_ID/status | jq -r '.status')
    if [ "$STATUS" = "completed" ]; then break; fi
    sleep 10
  done
  
  # 3. Generate materials
  curl -X POST http://localhost:8000/api/content/lectures/$LECTURE_ID/generate \
    -H "Content-Type: application/json" \
    -d '{"num_quiz_questions":20}'
  
  # 4. Wait for generation
  while true; do
    STATUS=$(curl -s http://localhost:8000/api/content/lectures/$LECTURE_ID/generation-status | jq -r '.status')
    if [ "$STATUS" = "completed" ]; then break; fi
    sleep 10
  done
  
  echo "✓ Lecture $NUM complete"
done
```

### Workflow 2: Regenerate Materials

If you want to regenerate materials (e.g., after improving prompts):

```bash
LECTURE_ID="550e8400-e29b-41d4-a716-446655440000"

# Just call generate again - it will overwrite existing materials
curl -X POST http://localhost:8000/api/content/lectures/$LECTURE_ID/generate \
  -H "Content-Type: application/json" \
  -d '{"num_quiz_questions":25}'
```

The database schema uses `UNIQUE(lecture_id)` constraints, so calling generate again will update (not duplicate) the materials.

## Tips

1. **Start small**: Test with 10 questions first, then scale up
2. **Monitor costs**: Each generation costs ~$0.30. Track via DeepSeek dashboard
3. **Check coverage**: Review coverage report to identify gaps
4. **Iterate prompts**: Adjust prompts in `backend/prompts/` to improve quality
5. **Use logs**: Check `logs/content_generation/` for debugging
