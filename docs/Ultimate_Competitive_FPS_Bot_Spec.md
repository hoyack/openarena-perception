# The Ultimate Competitive FPS Bot: A Modern Guide Specification

## Executive Summary

This document presents a comprehensive, game-agnostic specification for building the ultimate competitive FPS bot, synthesizing insights from the pioneering Quake III Arena Bot architecture with cutting-edge AI research from 2023-2025. This specification is designed to be adaptable across any FPS title, from arena shooters like Open Arena to tactical shooters and battle royale games.

---

## 1. Architectural Philosophy

### 1.1 Core Design Principles

| Principle | Description | Rationale |
|-----------|-------------|-----------|
| **Modularity** | Swappable components for game-specific adaptation | Enables cross-game compatibility |
| **Hybrid Intelligence** | Combine neural learning with symbolic reasoning | Best of both worlds: adaptability + interpretability |
| **Hierarchical Control** | Layered decision-making from strategic to tactical | Manages complexity, enables planning |
| **Emergent Behavior** | Complex behaviors from simple, composable rules | Natural, human-like play patterns |
| **Performance First** | Sub-millisecond decision times, minimal CPU overhead | Real-time gameplay requirements |

### 1.2 Layered Architecture (Modernized from Q3A)

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 5: META LEARNING & ADAPTATION                                │
│  - Continuous learning from gameplay                                 │
│  - Opponent modeling and adaptation                                  │
│  - Skill calibration for fair matches                                │
└─────────────────────────────────────────────────────────────────────┘
                                    ↕
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 4: TEAM COORDINATION & STRATEGY                              │
│  - Multi-agent coordination (CTDE MARL)                              │
│  - Strategic planning (HTN/MCTS)                                     │
│  - Dynamic role assignment                                           │
│  - Communication protocols                                           │
└─────────────────────────────────────────────────────────────────────┘
                                    ↕
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 3: CONSCIOUS DECISION MAKING                                 │
│  - High-level goal selection (Utility AI + GOAP)                     │
│  - Combat tactics (Behavior Trees)                                   │
│  - Situation assessment and threat evaluation                        │
└─────────────────────────────────────────────────────────────────────┘
                                    ↕
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 2: SUBCONSCIOUS PROCESSING                                   │
│  - Navigation and pathfinding (NavMesh + Polyanya)                   │
│  - Reactive behaviors (RVO, dodge patterns)                          │
│  - Perception filtering and attention                                │
│  - Memory management (LSTM/Transformer)                              │
└─────────────────────────────────────────────────────────────────────┘
                                    ↕
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1: PERCEPTION & ACTION                                       │
│  - Sensor fusion (vision, audio, symbolic)                           │
│  - World state representation                                        │
│  - Basic action execution                                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Perception System (Layer 1)

### 2.1 Sensor Architecture

The bot must abstract game-specific inputs into a unified perception layer:

| Sensor Type | Data Provided | Update Rate |
|-------------|---------------|-------------|
| **Visual** | Entity positions, types, visibility | 60 Hz |
| **Audio** | Footsteps, gunfire directions, explosions | 30 Hz |
| **Symbolic** | Game state (scores, timers, objectives) | 10 Hz |
| **Proprioceptive** | Self state (health, ammo, position) | 60 Hz |

### 2.2 Attention Mechanism

Implement a focus-based attention system:

```cpp
struct AttentionFocus {
    EntityID target;
    float priority;        // 0.0 - 1.0
    float confidence;      // Perception certainty
    Vec3 lastKnownPosition;
    float timeSinceLastSeen;
};

class AttentionSystem {
    std::vector<AttentionFocus> attentionStack;
    
    void UpdatePriorities() {
        // Threat-based priority
        // Proximity-based priority
        // Objective-based priority
        // Recency-based priority
    }
};
```

### 2.3 Memory System

Replace simple state tracking with a neural memory architecture:

**Short-Term Memory (Working Memory):**
- LSTM or GRU layers for temporal dependencies
- 128-256 hidden units
- Stores recent entity positions, actions, events

**Long-Term Memory (Episodic):**
- Transformer-based attention over past experiences
- Key events: deaths, kills, item timings, enemy patterns
- Enables prediction of enemy behavior

---

## 3. Navigation System (Layer 2)

### 3.1 Modern Navigation Architecture

**Replace Q3A's BSP-based AAS with:**

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Mesh Generation** | Recast (voxel-based) | Robust NavMesh from any geometry |
| **Pathfinding** | Polyanya or Lazy Theta* | Optimal any-angle paths |
| **Hierarchical** | HPA* | Fast long-distance queries |
| **Crowd Avoidance** | RVO2 | Reciprocal collision avoidance |
| **Mass Movement** | Flow Fields | RTS-scale unit coordination |

### 3.2 Dynamic Environment Handling

```cpp
class DynamicNavigationSystem {
    // Tile-based updates for destructible environments
    void MarkTileDirty(Bounds area);
    void RebuildDirtyTilesAsync();
    
    // Layered meshes for pre-computed destruction states
    NavMesh* GetMeshForDamageLevel(int level);
    
    // RVO for moving obstacles without mesh rebuilds
    RVO::Agent* AddDynamicObstacle(Vector3 pos, float radius);
};
```

### 3.3 Advanced Movement Patterns

**Beyond Q3A's circle strafing:**

| Pattern | Description | Use Case |
|---------|-------------|----------|
| **AD Spam** | Rapid direction changes | Throw off enemy aim |
| **Counter-Strafe** | Stop instantly for accuracy | Precision shots |
| **Bunny Hop** | Strafe-jump chains | Speed traversal |
| **Crouch Peeks** | Quick crouch-uncrouch | Safe angle checking |
| **Jiggle Peeks** | Minimal exposure peeks | Information gathering |

---

## 4. Decision Making (Layer 3)

### 4.1 Hybrid Decision Architecture

**Recommended: Utility AI + Behavior Trees + GOAP**

```
Utility System (High-Level Context)
    ↓
Evaluates: Combat, Retreat, Search, Objective
    ↓
Behavior Tree (Tactical Execution)
    ↓
Executes: Specific combat behaviors, positioning
    ↓
GOAP/HTN (Strategic Planning)
    ↓
Plans: Multi-step sequences for complex goals
```

### 4.2 Utility-Based Decision Making

Replace Q3A's fuzzy logic with modern utility curves:

```cpp
class UtilityEvaluator {
    float EvaluateCombatDesire() {
        float healthFactor = HealthCurve(health / maxHealth);
        float weaponFactor = WeaponPowerCurve(currentWeapon);
        float tacticalFactor = TacticalAdvantage();
        float enemyThreat = ThreatAssessment();
        
        return WeightedSum({
            {healthFactor, 0.3f},
            {weaponFactor, 0.25f},
            {tacticalFactor, 0.25f},
            {1.0f - enemyThreat, 0.2f}
        });
    }
};
```

### 4.3 Behavior Tree Structure

```yaml
CombatBehavior:
  type: Selector
  children:
    - type: Sequence
      name: FullAggression
      children:
        - Condition: { health > 50, hasAdvantage }
        - Task: PushAggressively
        
    - type: Sequence
      name: TakeCoverAndShoot
      children:
        - Condition: { underFire, coverAvailable }
        - Task: MoveToCover
        - Task: PopOutAndShoot
        
    - type: Sequence
      name: RetreatAndRecover
      children:
        - Condition: { health < 30 }
        - Task: FindRetreatPath
        - Task: MoveToSafety
```

---

## 5. Combat System

### 5.1 Aiming System

**Physics-Based Target Prediction:**

```cpp
Vector3 PredictTargetPosition(Entity target, float projectileSpeed) {
    // Iterative Newton-Raphson refinement
    float t = Distance(self.pos, target.pos) / projectileSpeed;
    
    for (int i = 0; i < 4; i++) {
        Vector3 predicted = target.pos + 
                           target.vel * t + 
                           target.accel * 0.5f * t * t;
        float dist = Distance(self.pos, predicted);
        t = dist / projectileSpeed;
    }
    
    return predicted;
}
```

**Human-Like Aiming Imperfections:**

| Imperfection | Implementation | Skill Impact |
|--------------|----------------|--------------|
| Reaction Time | 150-300ms delay | All levels |
| Overshoot | Initial overshoot with correction | Low-Medium |
| Perlin Noise | Smooth error patterns | All levels |
| Focus Drift | Accuracy decays during tracking | Low-Medium |
| Micro-corrections | Small adjustments | High |

### 5.2 Weapon Tactics

```cpp
class WeaponTactics {
    virtual AimPoint GetAimPoint(Target t) = 0;
    virtual float GetOptimalRange() = 0;
    virtual bool ShouldLead() = 0;
};

class RocketLauncherTactics : public WeaponTactics {
    AimPoint GetAimPoint(Target t) override {
        // Aim at feet for splash
        return t.position - Vec3(0, t.height * 0.4f, 0);
    }
    float GetOptimalRange() override { return 800.0f; }
    bool ShouldLead() override { return true; }
};
```

### 5.3 Cover System

**Tactical Position Selection (TPS):**

1. **Generation**: Collect candidate cover points
2. **Filtering**: Remove invalid positions (exposed, unreachable)
3. **Scoring**: Evaluate based on:
   - Distance to threat
   - Line of sight blocking
   - Escape routes
   - Shooting angles
   - Squad coordination

---

## 6. Team Coordination (Layer 4)

### 6.1 Multi-Agent Architecture

**Centralized Training, Decentralized Execution (CTDE):**

```cpp
// Training: Centralized critic sees all agents
class CentralizedCritic {
    float EvaluateGlobalState(GlobalState state, JointAction actions);
};

// Execution: Each agent acts on local observations
class DecentralizedPolicy {
    Action SelectAction(LocalObservation obs);
};
```

### 6.2 Communication System

**Replace Q3A's chat-based system with:**

| Method | Latency | Bandwidth | Use Case |
|--------|---------|-----------|----------|
| **Blackboard** | 0ms | High | Shared world model |
| **Learned Protocols** | 1-2ms | Low | Targeted communication |
| **Stigmergy** | 0ms | N/A | Indirect coordination |

**Blackboard Structure:**
```cpp
struct TeamBlackboard {
    // Shared knowledge
    Map<EntityID, EstimatedState> enemyEstimates;
    Map<ItemID, float> itemRespawnPredictions;
    
    // Task allocation
    Map<TaskID, AgentID> taskAssignments;
    Map<AgentID, TaskID> agentTasks;
    
    // Strategic state
    InfluenceMap teamInfluence;
    Strategy currentStrategy;
};
```

### 6.3 Dynamic Role Assignment

```cpp
class RoleAssignment {
    void AssignRoles() {
        for (auto agent : teamAgents) {
            float bestUtility = 0;
            Role bestRole;
            
            for (auto role : availableRoles) {
                float utility = EvaluateRoleUtility(agent, role);
                if (utility > bestUtility) {
                    bestUtility = utility;
                    bestRole = role;
                }
            }
            
            AssignRole(agent, bestRole);
        }
    }
};
```

---

## 7. Learning & Adaptation (Layer 5)

### 7.1 Training Pipeline

```
Phase 1: Behavior Cloning (Warm-start)
    ↓ Train on human demonstrations
Phase 2: Curriculum Learning
    ↓ Progressive difficulty increase
Phase 3: Self-Play
    ↓ Agents train against themselves
Phase 4: Population-Based Training
    ↓ Diverse opponent population
Phase 5: Human Fine-Tuning
    ↓ Adapt to human play styles
Phase 6: Deployment
    ↓ Continuous online learning
```

### 7.2 Reinforcement Learning Configuration

**For Discrete Actions (weapon selection, movement mode):**
```yaml
Algorithm: Rainbow DQN
Learning Rate: 0.0001
Batch Size: 32
Buffer Size: 100000
Gamma: 0.99
Target Update: 1000 steps
```

**For Continuous Actions (aiming, movement):**
```yaml
Algorithm: PPO
Learning Rate: 0.0003
Batch Size: 2048
Buffer Size: 20480
Epsilon: 0.2
Lambda: 0.95
```

**For Multi-Agent (team coordination):**
```yaml
Algorithm: MAPPO
Centralized Critic: true
Value Decomposition: QMIX-style
Communication: Learned (TarMAC-style)
```

### 7.3 Opponent Modeling

```cpp
class OpponentModel {
    // Classify opponent type
    enum OpponentType { AGGRESSIVE, DEFENSIVE, CAMPER, RUSHER };
    
    // Predict actions
    Action PredictAction(ObservationHistory history);
    
    // Adapt strategy
    void AdaptToOpponent(OpponentType type);
};
```

---

## 8. Game Adaptation Layer

### 8.1 Game-Specific Abstraction

Create a game adapter interface:

```cpp
class IGameAdapter {
    // Perception
    virtual std::vector<Entity> GetVisibleEntities() = 0;
    virtual GameState GetGameState() = 0;
    
    // Actions
    virtual void ExecuteAction(BotAction action) = 0;
    
    // Navigation
    virtual NavMesh* GetNavMesh() = 0;
    
    // Weapons
    virtual std::vector<WeaponInfo> GetAvailableWeapons() = 0;
};
```

### 8.2 Configuration System

```yaml
# game_config.yaml
game_type: "arena_shooter"  # or "tactical", "battle_royale"

physics:
  gravity: 800
  air_acceleration: 10
  ground_friction: 6

weapons:
  rocket_launcher:
    projectile_speed: 900
    splash_radius: 120
    self_damage: true
  
  railgun:
    hitscan: true
    damage: 100
    reload_time: 1.5

navigation:
  agent_radius: 16
  agent_height: 56
  max_slope: 45
```

---

## 9. Performance Requirements

### 9.1 Runtime Performance Budget

| Component | Max CPU Time | Max Memory |
|-----------|--------------|------------|
| Perception | 0.1ms | 1MB |
| Navigation | 0.5ms | 5MB |
| Decision Making | 0.2ms | 2MB |
| Combat AI | 0.3ms | 1MB |
| Team Coordination | 0.2ms | 2MB |
| **Total per bot** | **1.3ms** | **11MB** |

### 9.2 Neural Network Inference

| Model | Parameters | Inference Time (CPU) | Inference Time (GPU) |
|-------|------------|---------------------|---------------------|
| Movement Policy | 2M | 5ms | 1ms |
| Combat Policy | 1M | 3ms | 0.5ms |
| Memory (LSTM) | 500K | 2ms | 0.3ms |

---

## 10. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-4)
- [ ] Implement game adapter interface for target game
- [ ] Set up basic perception system
- [ ] Integrate Recast/Detour for navigation
- [ ] Create basic action execution layer

### Phase 2: Core AI (Weeks 5-8)
- [ ] Implement Utility AI for high-level decisions
- [ ] Build Behavior Tree framework
- [ ] Create weapon tactics system
- [ ] Implement aiming with human-like error

### Phase 3: Advanced Features (Weeks 9-12)
- [ ] Add cover system
- [ ] Implement advanced movement patterns
- [ ] Create memory system (LSTM)
- [ ] Build opponent modeling

### Phase 4: Team AI (Weeks 13-16)
- [ ] Implement blackboard system
- [ ] Create role assignment
- [ ] Add formation movement
- [ ] Build strategic planning (HTN)

### Phase 5: Learning (Weeks 17-20)
- [ ] Set up RL training environment
- [ ] Implement self-play pipeline
- [ ] Train initial policies
- [ ] Add population-based training

### Phase 6: Polish (Weeks 21-24)
- [ ] Performance optimization
- [ ] Skill calibration system
- [ ] Bot personality variations
- [ ] Extensive testing and balancing

---

## 11. Comparison: Q3A Bot vs Modern Specification

| Feature | Q3A Bot (2001) | Modern Specification (2025) |
|---------|----------------|----------------------------|
| **Navigation** | BSP-based AAS | Recast + Polyanya + RVO |
| **Pathfinding** | A* on areas | Any-angle + Hierarchical |
| **Decision Making** | Fuzzy Logic + FSM | Utility AI + BT + GOAP |
| **Memory** | Simple state | LSTM/Transformer |
| **Learning** | Genetic selection | Deep RL + Self-play |
| **Team Coordination** | Chat-based commands | CTDE MARL + Blackboard |
| **Communication** | Template matching | Learned protocols |
| **Aiming** | Linear leading | Physics prediction + ML |
| **Cover** | None | Full TPS system |
| **Movement** | Circle strafe | Adaptive patterns + Dodge |

---

## 12. References

### Foundational Works
1. van Waveren, J.M.P. "The Quake III Arena Bot" (2001)
2. Laird, J.E. "It Knows What You're Going to Do: Adding Anticipation to a QuakeBot" (1999)
3. Orkin, J. "The AI of F.E.A.R." (2006)

### Modern Research (2023-2025)
4. "Gunner: Playing FPS Game Doom with Scalable Deep Reinforcement Learning" (2025)
5. "Humanlike Behavior in a Third-Person Shooter with Imitation Learning" - IEEE CoG (2024)
6. "Beyond The Rainbow: High Performance Deep RL on Desktop PC" (2025)
7. "A Survey on Large Language Model-Based Game Agents" (2024)
8. "SPIRAL: Self-Play on Zero-Sum Games Incentivizes Reasoning" (2025)

### Open Source Resources
9. Recast Navigation: https://github.com/recastnavigation/recastnavigation
10. RVO2: https://gamma.cs.unc.edu/RVO2/
11. Stable-Baselines3: https://github.com/DLR-RM/stable-baselines3
12. Unity ML-Agents: https://github.com/Unity-Technologies/ml-agents

---

## Conclusion

This specification provides a comprehensive blueprint for building a competitive FPS bot that surpasses the capabilities of the pioneering Quake III Arena Bot while maintaining the design principles that made it successful. By combining modern deep learning, reinforcement learning, and multi-agent coordination with proven game AI techniques, this architecture can produce bots that are:

1. **Competitively viable** at high skill levels
2. **Human-like** in behavior and decision-making
3. **Adaptable** across different FPS titles
4. **Scalable** from individual bots to coordinated teams
5. **Trainable** through self-play and human demonstration

The modular, layered architecture ensures that individual components can be improved or replaced as AI research continues to advance, making this specification a living document for FPS bot development.

---

*Document Version: 1.0*
*Last Updated: April 2025*
*Target Games: Arena shooters, tactical FPS, battle royale*
