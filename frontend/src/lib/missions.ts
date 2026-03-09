import type { Node, Edge } from '@xyflow/react'

export interface MissionStep {
  id: string
  title: string
  description: string
  hint: string
  validate: (ctx: { nodes: Node[]; edges: Edge[] }) => boolean
  isManual?: boolean  // true = user clicks "Next" instead of auto-advance
}

export interface Mission {
  id: string
  title: string
  subtitle: string
  steps: MissionStep[]
  reward: string
}

export const MISSIONS: Mission[] = [
  {
    id: 'first_pipeline',
    title: 'BUILD YOUR FIRST PIPELINE',
    subtitle: 'Learn the basics by running AI locally',
    steps: [
      {
        id: 'welcome',
        title: 'Welcome to Blueprint',
        description: 'Blueprint lets you build AI/ML pipelines visually — drag blocks, connect them, and run. Let\'s build your first one.',
        hint: 'Click "Start" to begin.',
        validate: () => true,
        isManual: true,
      },
      {
        id: 'add_text_input',
        title: 'Add a Text Input Block',
        description: 'Every pipeline starts with data. Open the block library on the left sidebar and drag a "Text Input" block onto the canvas.',
        hint: 'Look in the SOURCE section of the block library.',
        validate: (ctx) => ctx.nodes.some((n: any) => n.data?.type === 'text_input'),
      },
      {
        id: 'add_llm',
        title: 'Add an LLM Block',
        description: 'Now add a language model to process your text. Drag an "LLM Inference" block onto the canvas.',
        hint: 'Look in the INFERENCE section, or search for "LLM".',
        validate: (ctx) => ctx.nodes.some((n: any) => n.data?.type === 'llm_inference'),
      },
      {
        id: 'connect_blocks',
        title: 'Connect the Blocks',
        description: 'Drag from the cyan output port at the bottom of Text Input to the cyan input port at the top of LLM Inference.',
        hint: 'Compatible ports glow when you hover near them.',
        validate: (ctx) => ctx.edges.length > 0,
      },
      {
        id: 'configure_prompt',
        title: 'Write Your Prompt',
        description: 'Click the LLM Inference block to open its config panel on the right. Type something in the "User Input" field.',
        hint: 'Try asking: "What is machine learning in one sentence?"',
        validate: (ctx) => {
          const llm = ctx.nodes.find((n: any) => n.data?.type === 'llm_inference')
          return !!(llm && (llm.data as any)?.config?.user_input?.length > 3)
        },
      },
      {
        id: 'run_pipeline',
        title: 'Run the Pipeline',
        description: 'Hit the green Run button in the top toolbar to execute your pipeline. Watch the blocks light up as they process.',
        hint: 'Make sure Ollama is running locally, or switch the backend to OpenAI/Anthropic.',
        validate: (ctx) => ctx.nodes.some((n: any) => ['complete', 'failed'].includes(n.data?.status)),
      },
      {
        id: 'celebrate',
        title: 'Mission Complete!',
        description: 'You just built and ran an AI pipeline. Check the Results tab to see the model\'s response. From here you can add evaluators, chain agents, or explore 85+ blocks.',
        hint: 'Next: try a Recipe from the Marketplace, or add an Evaluator block.',
        validate: () => true,
        isManual: true,
      },
    ],
    reward: 'First pipeline built and executed!',
  },
]

export function getMission(id: string): Mission | undefined {
  return MISSIONS.find((m) => m.id === id)
}
