export interface PaperTemplate {
  id: string
  name: string
  description: string
  sections: { title: string; type: string; content: string }[]
}

export const PAPER_TEMPLATES: PaperTemplate[] = [
  {
    id: 'icml',
    name: 'ICML',
    description: 'International Conference on Machine Learning',
    sections: [
      { title: 'Abstract', type: 'abstract', content: '' },
      { title: 'Introduction', type: 'introduction', content: '' },
      { title: 'Related Work', type: 'related_work', content: '' },
      { title: 'Methods', type: 'methods', content: '' },
      { title: 'Experiments', type: 'experiments', content: '' },
      { title: 'Results', type: 'results', content: '' },
      { title: 'Discussion', type: 'discussion', content: '' },
      { title: 'Conclusion', type: 'conclusion', content: '' },
      { title: 'References', type: 'references', content: '' },
    ],
  },
  {
    id: 'neurips',
    name: 'NeurIPS',
    description: 'Neural Information Processing Systems',
    sections: [
      { title: 'Abstract', type: 'abstract', content: '' },
      { title: 'Introduction', type: 'introduction', content: '' },
      { title: 'Background', type: 'related_work', content: '' },
      { title: 'Problem Formulation', type: 'methods', content: '' },
      { title: 'Proposed Method', type: 'methods', content: '' },
      { title: 'Theoretical Analysis', type: 'analysis', content: '' },
      { title: 'Experiments', type: 'experiments', content: '' },
      { title: 'Results & Discussion', type: 'results', content: '' },
      { title: 'Broader Impact', type: 'discussion', content: '' },
      { title: 'Conclusion', type: 'conclusion', content: '' },
      { title: 'References', type: 'references', content: '' },
    ],
  },
  {
    id: 'acl',
    name: 'ACL',
    description: 'Association for Computational Linguistics',
    sections: [
      { title: 'Abstract', type: 'abstract', content: '' },
      { title: 'Introduction', type: 'introduction', content: '' },
      { title: 'Related Work', type: 'related_work', content: '' },
      { title: 'Task & Data', type: 'methods', content: '' },
      { title: 'Model Architecture', type: 'methods', content: '' },
      { title: 'Experimental Setup', type: 'experiments', content: '' },
      { title: 'Results', type: 'results', content: '' },
      { title: 'Analysis', type: 'analysis', content: '' },
      { title: 'Conclusion', type: 'conclusion', content: '' },
      { title: 'Limitations', type: 'discussion', content: '' },
      { title: 'References', type: 'references', content: '' },
    ],
  },
  {
    id: 'custom',
    name: 'Custom',
    description: 'Start with a blank paper',
    sections: [
      { title: 'Introduction', type: 'introduction', content: '' },
      { title: 'Methods', type: 'methods', content: '' },
      { title: 'Results', type: 'results', content: '' },
      { title: 'Conclusion', type: 'conclusion', content: '' },
    ],
  },
  {
    id: 'ablation',
    name: 'Ablation Study',
    description: 'Template for systematic ablation analysis',
    sections: [
      { title: 'Overview', type: 'introduction', content: '' },
      { title: 'Baseline Configuration', type: 'methods', content: '' },
      { title: 'Component Analysis', type: 'experiments', content: '' },
      { title: 'Ablation Results', type: 'results', content: '' },
      { title: 'Key Findings', type: 'analysis', content: '' },
      { title: 'Recommendations', type: 'conclusion', content: '' },
    ],
  },
]
