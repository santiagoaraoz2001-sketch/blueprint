import { memo } from 'react'
import { NodeResizer } from '@xyflow/react'
import { T, F, FS } from '@/lib/design-tokens'

export default memo(function GroupNode({ data, selected }: any) {
    return (
        <>
            <NodeResizer
                color={T.cyan}
                isVisible={selected}
                minWidth={200}
                minHeight={150}
            />
            <div
                style={{
                    width: '100%',
                    height: '100%',
                    background: `${T.surface1}40`,
                    border: `1px solid ${selected ? T.cyan : T.border}`,
                    borderRadius: 8,
                    position: 'relative',
                }}
            >
                <div
                    style={{
                        position: 'absolute',
                        top: -10,
                        left: 10,
                        background: T.surface2,
                        padding: '2px 8px',
                        borderRadius: 4,
                        border: `1px solid ${selected ? T.cyan : T.border}`,
                        color: T.dim,
                        fontFamily: F,
                        fontSize: FS.xs,
                        fontWeight: 600,
                    }}
                >
                    {data.label || 'Sub-Flow Group'}
                </div>
            </div>
        </>
    )
})
